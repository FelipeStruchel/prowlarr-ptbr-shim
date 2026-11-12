# Contribuindo

## Arquitetura

```
server.py            # entrypoint: HTTP handler + main()
config.py            # DEFAULTS, load_config/apply_config, dict CFG compartilhado
utils/
  cache.py            # cache em memoria com TTL
  http.py             # wrapper urllib (User-Agent, retries)
  text.py             # norm, fuzzy_pattern, strip_tags, size_to_bytes
  logging_setup.py     # logger "shim" (arquivo rotativo + stdout)
tmdb.py               # resolve_titles(): traduz a busca via TMDB (pt-BR)
scraper.py            # motor: busca nos sources, abre posts, monta releases
prowlarr.py           # fanout opcional: reaproveita a traducao nos outros indexadores
torznab.py            # caps/erro/resultados em XML (protocolo Torznab)
sources/
  __init__.py          # auto-descoberta dos sources (load_sites())
  <site_id>.py          # um arquivo por site, ver abaixo
  _template.py          # modelo para copiar
scripts/
  new_source.py          # gera sources/<site_id>.py a partir do template
```

A ideia central: **toda busca tem a mesma entrada (um termo de busca) e a
mesma saída (lista de releases no mesmo formato)**. Cada arquivo em
`sources/` é só o "meio" - ele descreve, via regex, como extrair cards de
resultado e seus magnets do HTML daquele site específico. Toda a lógica de
busca, cache, threading e montagem do release é compartilhada em
`scraper.py` e nunca precisa ser tocada para adicionar um site.

## Adicionando um site novo

1. Gere o arquivo a partir do template:

   ```
   python scripts/new_source.py <site_id> "Nome do Site" https://site.com
   ```

   `site_id` é o nome do arquivo (ex.: `meusite` -> `sources/meusite.py`) e
   também o valor usado em `config.json` -> `"sites": [...]`.

2. Abra o site no navegador, faça uma busca (`/?s=termo`) e veja o HTML real
   da página (não assuma a estrutura - sites mudam o markup com frequência).
   Preencha em `sources/<site_id>.py`:
   - `card_re`: isola o bloco HTML de **um** card de resultado.
   - `title_re`: dentro do bloco, captura `(url_do_post, titulo)`.
   - `year_re`: dentro do bloco, captura o ano (pode não casar - cards sem
     ano ainda são aceitos).
   - `movie_path` / `tv_path`: paths das páginas de listagem (usadas só pelo
     feed de "últimos posts" que o Prowlarr usa pra testar o indexador).

3. Adicione `site_id` em `sites` no seu `config.json` (ou deixe de fora pra
   testar primeiro - sources fora da lista continuam carregados, só não são
   usados nas buscas).

4. Teste localmente: suba o servidor (`python server.py`) e faça uma busca
   contra `/api?t=search&apikey=...&q=<algum titulo que sabe que existe la>`.
   Confirme que o magnet final é válido antes de considerar pronto.

### O que **não** adicionar

Sites cujo magnet só aparece depois de passar por um link locker/encurtador
de anúncio (precisa "ver um anúncio" pra liberar o link real) **não devem
ser integrados aqui**. Além de violar a política de inclusão de indexadores
do Jackett/Prowlarr, esses mecanismos são feitos pra quebrar automação e
mudam sem aviso. Só vale a pena um site cujo magnet apareça direto no HTML
do post (ou numa API/feed do próprio site, tipo o feed JSON do Blogger).

## Contrato do `SITE`

Cada módulo de `sources/` (exceto os que começam com `_`) precisa expor um
dict `SITE` com estes campos:

| campo | tipo | o que é |
|---|---|---|
| `name` | `str` | nome exibido (aparece como "indexer" no resultado) |
| `base_url` | `str` | raiz do site, sem barra final |
| `movie_path` | `str` | path da listagem de filmes |
| `tv_path` | `str` | path da listagem de séries |
| `card_re` | `re.Pattern` (compilado com `re.S`) | isola o bloco de um card |
| `title_re` | `re.Pattern` | captura `(url, titulo)` dentro do card |
| `year_re` | `re.Pattern` | captura o ano dentro do card (opcional) |

## Tratamento de erro (propositalmente resiliente)

- **Erro na importação do módulo** (sintaxe, regex inválido, campo
  faltando): `sources/__init__.py` loga um `ERROR` e ignora aquele source -
  o servidor sobe normalmente com os demais.
- **Erro durante uma busca/fetch** (site fora do ar, timeout, HTML mudou e o
  regex não casa mais): cada chamada de rede já está dentro de um
  `try/except` que loga um `WARNING` e segue com os outros sources/termos.
  Nenhum erro de um site derruba a busca inteira.
- Timeout por requisição a um source é configurável em `site_timeout`
  (`config.json`, default 15s), pra um site lento não travar a busca toda.

Isso significa que, ao testar um source novo, um regex errado só aparece no
log - não quebra nada pra quem já está usando o shim.
