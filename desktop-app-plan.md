# Desktop PDF Translator – Plano para App Desktop (Windows 11)

Este guia resume como transformar o projeto atual em um aplicativo desktop para Windows 11 com **experiência realmente nativa**, mantendo o backend FastAPI atual e adicionando integração com recursos do sistema operacional.

- Janela própria com visual alinhado ao Windows 11 (cantos arredondados, tema escuro, título claro).
- Backend FastAPI reaproveitado (sem depender de nuvem).
- Opção de usar:
  - LLM local (Ollama).
  - LLM em nuvem via API com chave.
- Fluxo de tradução em **uma única janela**: upload, acompanhamento de progresso e download/salvamento final.

## 1. Arquitetura geral do app desktop

- Mantemos o **backend FastAPI** exatamente como hoje:
  - `app/main.py` com `create_app`.
  - Rotas de UI (Jinja2) e rotas de API.
  - `JobService` tratando PDF, páginas, tradução e geração do PDF traduzido.
- Para o desktop:
  - Um processo Python inicia o servidor uvicorn em `http://127.0.0.1:8000`.
  - Uma **janela própria** é aberta usando um webview apontando para `http://127.0.0.1:8000`.
  - O usuário interage com a UI como se fosse um app Windows 11, mas tudo roda local.

Resultado:

- Não precisa de Render nem infra em nuvem para o app desktop.
- Só precisa de LLM:
  - local (Ollama) ou
  - remoto (API com chave).

### 1.1 Características de app “nativo” Windows 11

O objetivo é que o usuário perceba o app como nativo, não como “site aberto num navegador”. Para isso:

- Executável único (`run_desktop.exe`) com:
  - Ícone próprio do aplicativo.
  - Sem console preto (modo janela apenas).
- Janela com:
  - Cantos arredondados.
  - Tema escuro (preto + verde) alinhado ao que já foi feito na UI.
  - Botões de fechar, maximizar e minimizar padrão do Windows 11.
- Integração com recursos do sistema:
  - Diálogo padrão do Windows para **escolher onde salvar o PDF traduzido**.
  - (Futuro) Associação de arquivo `.pdf` para abrir o app ao clicar em PDFs, se desejado.
  - (Futuro) Atalhos no menu Iniciar e fixar na barra de tarefas.

## 2. Dependências adicionais para o modo desktop

Além das dependências já existentes no projeto (FastAPI, uvicorn, Jinja2, etc.), para o desktop serão usadas:

- `pywebview` (janela nativa com webview).
- `pyinstaller` (criar o `.exe`).

Instalação sugerida em ambiente local:

```bash
cd c:\projects\translater
pip install pywebview pyinstaller
```

Se quiser fixar no projeto:

- Adicionar `pywebview` e `pyinstaller` no `requirements-dev.txt` (quando existir) ou tratar como dependências de desenvolvimento.

## 3. Script de inicialização do desktop (`run_desktop.py`)

Objetivo do script:

- Subir o servidor uvicorn com `create_app`.
- Abrir uma janela desktop (WebView) apontando para `http://127.0.0.1:8000`.
- Expor funções Python para o front-end poder:
  - pedir ao sistema um diálogo “Salvar como…” para o PDF.
  - no futuro, abrir configurações, logs, etc.
- Fechar o servidor quando a janela for encerrada.

Fluxo planejado:

1. Importar `uvicorn`, `threading` e `webview` (pywebview).
2. Iniciar o uvicorn em uma thread separada:
   - host `127.0.0.1`.
   - port `8000`.
   - usando `app.main:create_app` com `factory=True`.
3. Criar uma classe Python exposta ao WebView, por exemplo `DesktopApi`, com métodos:
   - `save_translated_pdf(job_id: str)`: baixa o PDF do backend e abre o diálogo de salvar.
4. Usar `pywebview` para criar uma janela:
   - título `"PDF Translator"`.
   - URL `"http://127.0.0.1:8000"`.
   - tamanho inicial, por exemplo `1200x800`, com redimensionamento habilitado.
   - backend Edge/Chromium no Windows (config padrão moderna do pywebview).
   - API exposta: instância de `DesktopApi`.
5. Ao fechar a janela:
   - sinalizar para o uvicorn encerrar (por exemplo, usando um `Event` de threading).

Exemplo de estrutura de `run_desktop.py` (esqueleto, sem detalhes de erro/log):

```python
import threading
from pathlib import Path

import requests
import uvicorn
import webview

from app.main import create_app


class DesktopApi:
    def save_translated_pdf(self, job_id: str) -> None:
        # Esta função será chamada pelo front-end via window.pywebview.api.save_translated_pdf(jobId)
        from tkinter import Tk
        from tkinter.filedialog import asksaveasfilename

        backend_url = f"http://127.0.0.1:8000/api/jobs/{job_id}/download"

        response = requests.get(backend_url, timeout=60)
        response.raise_for_status()

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        save_path = asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            title="Save translated PDF",
        )

        root.destroy()

        if not save_path:
            return

        path_obj = Path(save_path)
        path_obj.write_bytes(response.content)


def start_server() -> None:
    uvicorn.run(
        "app.main:create_app",
        host="127.0.0.1",
        port=8000,
        factory=True,
        log_level="info",
    )


if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    api = DesktopApi()
    webview.create_window(
        "PDF Translator",
        "http://127.0.0.1:8000",
        width=1200,
        height=800,
        resizable=True,
        js_api=api,
    )
    webview.start()
```

No front-end (templates), em vez de apenas fazer `window.location.href` para baixar o PDF, podemos:

- Detectar se estamos em modo desktop (por exemplo, checando se `window.pywebview` existe).
- Se existir:
  - chamar `window.pywebview.api.save_translated_pdf(jobId)`.
- Senão:
  - manter o fluxo atual de download automático pelo navegador.

Isso permite compatibilidade com:

- modo “puro navegador” (dev durante desenvolvimento ou uso web); e
- modo desktop empacotado, com experiência Windows 11 e escolha da pasta de salvamento.

## 4. Seleção de backend de LLM (local ou API paga)

O `TranslationClient` já usa variáveis de ambiente:

- `TRANSLATION_LLM_BASE_URL`
- `TRANSLATION_LLM_MODEL_NAME`

Para suportar bem desktop + LLM local ou API paga, o plano é:

1. Adicionar uma variável de ambiente ou arquivo de configuração, por exemplo:
   - `TRANSLATION_BACKEND_PROVIDER` com valores:
     - `"local_ollama"` – usar Ollama na máquina (default atual).
     - `"remote_api"` – usar API de LLM/Tradução em nuvem.
2. Para `"local_ollama"`:
   - `TRANSLATION_LLM_BASE_URL` continua algo como:
     - `http://localhost:11534` (Ollama local).
   - Sem chave de API.
3. Para `"remote_api"`:
   - `TRANSLATION_LLM_BASE_URL` aponta para o endpoint HTTPS da API.
   - Uma `TRANSLATION_API_KEY` é usada em header de autorização.
   - O corpo do request será adaptado ao formato da API escolhida.

Possível fluxo na UI (futuro):

- Tela de configurações simples para:
  - escolher “LLM local” ou “LLM em nuvem (API)”;
  - configurar a URL de API;
  - informar a chave de API.

## 5. Empacotamento em `.exe` com PyInstaller

Depois de o `run_desktop.py` estar implementado e testado, o empacotamento padrão para Windows será:

1. No diretório do projeto:

```bash
cd c:\projects\translater
pyinstaller --onefile --windowed run_desktop.py
```

2. O parâmetro `--windowed` evita abrir o console preto ao iniciar o app.
3. O executável gerado ficará normalmente em:
   - `dist\run_desktop.exe`

Esse `.exe` pode ser distribuído para usuários Windows:

- Ao abrir:
  - inicia o servidor FastAPI local,
  - abre a janela com a UI,
  - e permite traduções usando o backend de LLM configurado.

## 6. Integração com LLM local (Ollama)

Para o modo desktop com LLM local:

- O usuário precisa ter Ollama instalado na máquina.
- O app pode:
  - tentar detectar se o endpoint `http://localhost:11434` ou `http://localhost:11534` está respondendo;
  - exibir uma mensagem amigável se o LLM não estiver disponível.

Checklist para o usuário:

1. Instalar Ollama.
2. Baixar o modelo desejado (ex.: `translategemma`).
3. Manter o Ollama rodando (normalmente o serviço sobe automaticamente).
4. Abrir o app desktop.

## 7. Integração com LLM em nuvem (API paga)

Para quem tiver uma key de LLM em nuvem:

- O app desktop deve permitir configurar:
  - endpoint da API;
  - chave de API;
  - (opcional) modelo a ser usado.
- O `TranslationClient` passará a:
  - enviar requisições HTTPS para a API;
  - incluir a chave em um header (`Authorization`, por exemplo);
  - adaptar o JSON de request/response ao contrato da API.

Vantagens:

- Usuários com boa conexão podem usar IA em nuvem sem sobrecarregar a máquina local.
- Você não precisa hospedar o LLM; apenas integra via API.

## 8. Roadmap resumido

1. Criar `run_desktop.py` com:
   - inicialização do uvicorn em thread;
   - janela `pywebview` para `http://127.0.0.1:8000`.
2. Testar o app desktop em modo “LLM local”:
   - com Ollama rodando.
3. Adaptar `TranslationClient` para suportar:
   - `TRANSLATION_BACKEND_PROVIDER` (`local_ollama` ou `remote_api`);
   - envs para API remota (`TRANSLATION_API_KEY`, `TRANSLATION_API_URL`).
4. Adicionar uma tela de configurações na UI para:
   - escolher backend;
   - informar chave de API.
5. Empacotar com PyInstaller em `.exe`:
   - testar em máquinas Windows limpas (sem ambiente de dev).

Este arquivo serve como referência rápida para implementar e manter o modo desktop do projeto sem depender de nuvem.

