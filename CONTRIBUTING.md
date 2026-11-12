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
  _common.py            # helpers reaproveitaveis p/ sources baseados em regex sobre HTML
  <site_id>.py          # um arquivo por site, ver abaixo
  _template.py          # modelo/documentacao do contrato
scripts/
  new_source.py          # gera sources/<site_id>.py com o esqueleto de regex_source
```

A ideia central: **toda busca tem a mesma entrada (um termo) e a mesma
saída (cards/magnets no mesmo formato)** - o que um source faz por dentro
pra chegar lá não importa pro resto do sistema. Isso é o que torna um
source plug-and-play: ele é só o "meio" entre a query e a resposta.
Concretamente, um módulo em `sources/` expõe um dict `SOURCE` com:

- `name` (`str`): nome exibido (aparece como "indexer" no resultado).
- `search(term)` -> lista de cards `{url, title, year, is_tv, site}`.
- `fetch_post(card)` -> `{orig, pub, magnets: [{href, anchor, before}, ...]}`.
- `latest(is_tv)` (opcional) -> lista de cards, só usada pelo feed de
  "últimos posts" que o Prowlarr usa pra testar o indexador.

Como `search`/`fetch_post` são implementados é **livre** - regex sobre
HTML, uma API JSON do próprio site (como o feed do Blogger), scraping com
browser, o que for. Toda a lógica compartilhada (montar o nome do release
a partir do magnet, filtrar por título/ano/temporada, cache, threading,
dedup) fica em `scraper.py` e nunca precisa ser tocada pra adicionar um
site - ela só conhece o contrato acima, não como ele foi cumprido.

## Adicionando um site novo

### Caso comum: HTML simples com regex

A maioria dos sites publica o magnet direto no HTML do post e tem uma
página de busca (`/?s=termo`) com uma lista de "cards". Pra esse caso,
`sources/_common.py` já tem tudo pronto via `regex_source(...)`.

1. Gere o arquivo:

   ```
   python scripts/new_source.py <site_id> "Nome do Site" https://site.com
   ```

   `site_id` é o nome do arquivo (ex.: `meusite` -> `sources/meusite.py`) e
   também o valor usado em `config.json` -> `"sites": [...]`.

2. Abra o site no navegador, faça uma busca e veja o HTML real da página
   (não assuma a estrutura - sites mudam o markup com frequência). Preencha
   em `sources/<site_id>.py`:
   - `card_re`: isola o bloco HTML de **um** card de resultado.
   - `title_re`: dentro do bloco, captura `(url_do_post, titulo)`.
   - `year_re`: dentro do bloco, captura o ano (pode não casar - cards sem
     ano ainda são aceitos).
   - `movie_path` / `tv_path`: paths das páginas de listagem.

3. Adicione `site_id` em `sites` no seu `config.json` (ou deixe de fora pra
   testar primeiro - sources fora da lista continuam carregados, só não são
   usados nas buscas).

### Caso customizado: site que não encaixa no padrão regex

Se o site exige outra coisa (paginação própria, uma API, scraping com
browser, múltiplas requisições por busca...), ignore `regex_source` e
escreva `search`/`fetch_post` do seu jeito em `sources/<site_id>.py`,
respeitando só o formato de entrada/saída acima. Dá pra reaproveitar
`sources._common.parse_cards`/`fetch_post_html` dentro da sua própria
função se só uma parte do fluxo for diferente. Ver a opção 2 em
`sources/_template.py` para o esqueleto.

### Testando

Suba o servidor (`python server.py <config de teste>`) e faça uma busca
contra `/api?t=search&apikey=...&q=<algum título que sabe que existe lá>`.
Confirme que o magnet final é válido antes de considerar pronto.

### O que **não** adicionar

Sites cujo magnet só aparece depois de passar por um link locker/encurtador
de anúncio (precisa "ver um anúncio" pra liberar o link real) **não devem
ser integrados aqui**. Além de violar a política de inclusão de indexadores
do Jackett/Prowlarr, esses mecanismos são feitos pra quebrar automação e
mudam sem aviso. Só vale a pena um site cujo magnet apareça direto no HTML
do post (ou numa API/feed do próprio site, tipo o feed JSON do Blogger).

## Tratamento de erro (propositalmente resiliente)

- **Erro na importação do módulo** (sintaxe, campo faltando, `SOURCE`
  ausente): `sources/__init__.py` loga um `ERROR` e ignora aquele source -
  o servidor sobe normalmente com os demais.
- **Erro durante uma busca/fetch** (site fora do ar, timeout, HTML mudou e o
  regex não casa mais, API mudou): cada chamada já está dentro de um
  `try/except` que loga um `WARNING` e segue com os outros sources/termos.
  Nenhum erro de um site derruba a busca inteira.
- Timeout por requisição a um source é configurável em `site_timeout`
  (`config.json`, default 15s) - usado pelos helpers de `_common.py`; um
  source 100% customizado é responsável por aplicar seu próprio timeout.

Isso significa que, ao testar um source novo, um erro só aparece no log -
não quebra nada pra quem já está usando o shim.
