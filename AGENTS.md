# AGENTS.md

Guia rápido pra agentes de IA trabalhando neste repo. Detalhes completos (arquitetura,
contrato do `SOURCE`, como adicionar um source) estão em [CONTRIBUTING.md](CONTRIBUTING.md).

## O que é

Shim Torznab (stdlib Python, sem dependências) que raspa sites PT-BR de torrent e expõe
pro Prowlarr. Ver [README.md](README.md) para visão geral e config.

## Rodando localmente

```
python server.py                    # usa config.json da raiz
python server.py caminho/outro.json  # config alternativo
```

Nunca rode usando o `config.json` real do usuário para testes - ele tem uma chave TMDB de
verdade. Para testar, copie para um config temporário fora do repo (ou em uma pasta de
scratch), com `tmdb_api_key: ""` e `prowlarr.enabled: false`, e passe esse caminho como
argumento. Teste checando a sintaxe (`python -c "import ast; ast.parse(open(f).read())"`)
e, se possível, subindo o servidor e batendo em `/api?t=caps` e `/api?t=search&...`.

## Convenções do código

- Sem dependências externas - só biblioteca padrão.
- Sem comentários explicando o óbvio; comentário só quando a razão não é óbvia pelo código
  (ex.: por que um regex tem um lookahead específico).
- `CFG` (em `config.py`) é um dict compartilhado, mutado em-lugar (`clear()`+`update()`) -
  nunca reatribua `CFG = {...}` em outro módulo, isso quebraria a referência compartilhada.
- Logger único, `logging.getLogger("shim")`, em todos os módulos.

## Adicionando um source novo

Contrato fixo (não muda): `search(term) -> cards`, `fetch_post(card) -> post`, `latest(is_tv)`
opcional - ver CONTRIBUTING.md. Pra um site com HTML simples, use
`python scripts/new_source.py <site_id> "Nome" https://site.com` e preencha os regexes
olhando o HTML real do site (nunca assuma a estrutura). Pra um site que não encaixa nesse
padrão (API própria, paginação diferente, etc.), escreva `search`/`fetch_post` direto, sem
usar `regex_source` - o resto do motor (`scraper.py`) não precisa saber a diferença. **Nunca**
adicione um site cujo magnet só é liberado depois de um link locker/anúncio - ver a seção
correspondente em CONTRIBUTING.md antes de propor um source assim.

## Antes de considerar uma mudança pronta

- `ast.parse` em todo arquivo `.py` tocado.
- Se mudou `scraper.py`, `sources/*` ou `config.py`: suba o servidor com um config de teste
  e confirme que uma busca real ainda devolve resultados e magnets válidos.
- Nunca commite `config.json` ou `shim.log` (já estão no `.gitignore`).
