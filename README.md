# prowlarr-ptbr-shim

Shim Torznab que raspa sites brasileiros de torrent e expõe os resultados para
o [Prowlarr](https://wiki.servarr.com/prowlarr) (e, por consequência,
Radarr/Sonarr) como um indexador comum. Resolve o título em PT-BR via TMDB e,
opcionalmente, reaproveita essa tradução para buscar nos outros indexadores já
cadastrados no Prowlarr.

Só biblioteca padrão do Python, sem dependências externas.

## Como funciona, resumido

1. Prowlarr chama `GET /api?t=...` nesse shim como se fosse qualquer outro
   indexador Torznab.
2. O título da busca é resolvido via TMDB (título original + título PT-BR).
3. Cada site cadastrado em `sources/` é buscado em paralelo com os dois
   títulos; os cards encontrados são filtrados por nome/ano/temporada.
4. O post de cada card é aberto para extrair os magnets reais e montar o
   release (nome, infohash, tamanho, resolução, etc.).
5. Se `prowlarr.enabled` estiver ligado, o título PT-BR também é buscado nos
   demais indexadores do Prowlarr (fanout), já que eles não acham o conteúdo
   pelo nome original.
6. Tudo é devolvido como um único feed Torznab.

Arquitetura completa (e como adicionar um site novo) está no
[CONTRIBUTING.md](CONTRIBUTING.md).

## Instalação

1. Copie `config.example.json` para `config.json` e preencha:
   - `tmdb_api_key`: chave da [API do TMDB](https://www.themoviedb.org/settings/api)
     (v3 ou v4/Bearer). Sem ela a tradução PT-BR fica desligada.
   - `torznab_apikey`: qualquer string, é a apikey que o Prowlarr vai usar.
   - `prowlarr.*`: se quiser o fanout para os outros indexadores (opcional).
2. Rode:

   ```
   python server.py
   ```

   (ou `python server.py caminho/para/outro_config.json` para usar um config
   alternativo).
3. No Prowlarr, cadastre um indexador Torznab apontando para
   `http://127.0.0.1:9797/api` com a apikey configurada.

## Config

Campos de `config.json` (todos opcionais, os defaults estão em `config.py`):

| campo | default | o que faz |
|---|---|---|
| `host` / `port` | `127.0.0.1:9797` | onde o shim escuta |
| `torznab_apikey` | `ptbr-shim` | apikey que o Prowlarr deve usar |
| `tmdb_api_key` | `""` | chave do TMDB; vazio desliga a tradução |
| `sites` | os 3 sources atuais | quais arquivos de `sources/` ficam ativos |
| `site_timeout` | `15` (segundos) | timeout por requisição a um source |
| `cache_minutes` | `360` | TTL do cache em memória |
| `max_posts` | `8` | quantos posts são abertos por busca |
| `rewrite_titles` | `true` | troca o nome PT-BR do release pelo original |
| `assume_source` | `BluRay` | fonte assumida quando não dá pra detectar |
| `language_tag` | `Brazilian` | tag adicionada em releases dual/dublado |
| `prowlarr` | — | config do fanout opcional pros outros indexadores |

## Logs

Tudo vai para `shim.log` (rotativo, 1MB x 2 backups) e para stdout.
