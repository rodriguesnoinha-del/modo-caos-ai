# Backend Modo Caos AI (MVP)

Este backend gera cortes verticais reais a partir de arquivos enviados com autorização. Não baixa vídeos por URL e não publica automaticamente. Com `faster-whisper` opcional, prioriza janelas com maior densidade de fala e exporta legendas `.srt`; sem ele, gera trechos espaçados, sem legendas. Não faz análise de viralidade.

## Executar em computador/servidor

1. Instale Python 3.11+, FFmpeg e FFprobe.
2. `pip install -r requirements.txt`
3. Para transcrição: `pip install faster-whisper` (o modelo é baixado no primeiro uso).
4. Configure `MODO_CAOS_TOKEN` com uma senha longa e `ALLOWED_ORIGINS=https://SEUUSUARIO.github.io`.
5. Execute `uvicorn app:app --host 0.0.0.0 --port 8000` dentro da pasta backend.
6. Para acessar pelo site HTTPS, publique a API também com HTTPS, em serviço que permita CPU, disco temporário e FFmpeg. A hospedagem pode ter custos. Não exponha token no repositório ou no HTML.

Limitações: máximo 500 MB por upload, até 8 cortes por pedido; não há fila, limpeza automática de arquivos, autenticação multiusuário nem limite de requisições. Para uso permanente na internet, adicionar proxy HTTPS, rate limiting, fila, limpeza agendada e armazenamento privado. O token é inserido pelo usuário no navegador a cada sessão, sem salvar no GitHub.
