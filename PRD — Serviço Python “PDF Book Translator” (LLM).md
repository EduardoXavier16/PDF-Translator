<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

## PRD — Serviço Python “PDF Book Translator” (LLM)

### 1) Visão do produto

O produto permite que um usuário envie um **PDF grande** (ex.: 700 páginas) e receba um arquivo **PDF e/ou EPUB** traduzido para um idioma escolhido, com rastreabilidade por página/bloco e execução assíncrona (fila) para não estourar tempo de request nem limites de contexto da LLM.[^1][^2]

### 2) Objetivos e não-objetivos

**Objetivos**

- Suportar PDFs “digitais” (texto selecionável) e PDFs “escaneados” (OCR).[^1]
- Traduzir mantendo o máximo possível de estrutura (títulos, parágrafos, tabelas quando viável) usando elementos/metadata como “fonte da verdade”, não Markdown.[^3][^2]
- Permitir reprocessamento parcial (retry por bloco/página) e checkpointing para jobs longos.[^2]

**Não-objetivos (MVP)**

- Reproduzir layout pixel-perfect do PDF original em todos os casos (múltiplas colunas/tabelas complexas podem variar).[^1]
- Tradução de imagens/figuras com texto embutido (pode entrar em uma fase 2 com OCR em imagens recortadas).[^1]

***

## 3) Usuários e casos de uso

- Leitor/pesquisador: enviar livro técnico e baixar PDF/EPUB traduzido.
- Editor: traduzir capítulos e revisar; precisa de rastreio por página/bloco.[^2]

***

## 4) Requisitos funcionais

### 4.1 Upload e criação de job

- Endpoint `POST /jobs` recebe: arquivo PDF, `source_lang` (opcional auto), `target_lang`, modo de extração (`auto|fast|hi_res|ocr_only`), formato de saída (`pdf|epub|both`). [^1][^3]
- Retorna `job_id` imediatamente e processa em background.


### 4.2 Processamento do PDF (extração → elementos)

- Extrair conteúdo com **Unstructured** `partition_pdf`, com opção de `strategy` e `include_page_breaks`.[^4][^1]
- Cada elemento deve armazenar: `element_id`, `type`, `text`, `metadata` (incl. page, posição, etc. quando disponível).[^2]
- Habilitar `unique_element_ids=True` quando quiser IDs globalmente únicos (útil como PK no banco).[^5][^2]


### 4.3 Chunking (unidade de tradução)

- Unidade padrão: **um “element” por vez** (Title/NarrativeText/ListItem/Table etc.), com regra de agrupamento opcional “por página” se ficar muito fragmentado.[^2][^1]
- Não usar “parágrafo detectado por regex” como base principal, porque PDF é layout-based e pode embaralhar ordem/colunas.[^6][^1]


### 4.4 Tradução com LLM

- Para cada elemento com `text`:
    - Prompt: “traduza fielmente, não adicione conteúdo; preserve números, unidades e siglas; se o trecho estiver ilegível/incompleto, retorne um marcador”.
    - Persistir `source_text`, `translated_text`, `model`, `prompt_version`, `tokens/cost` (se disponível), `status`.
- Para tabelas: se o Unstructured fornecer `text_as_html` (quando aplicável), traduzir mantendo HTML e re-render depois.[^7][^3]


### 4.5 Validação anti-alucinação (MVP)

- Regras automáticas por elemento:
    - Se `source_text` contém muitos números/IDs, verificar se aparecem na tradução (heurística).
    - Se o elemento for muito curto (ex.: 1–3 caracteres), não “inventar”; só repetir ou marcar ilegível.
- Auditoria: armazenar `page_number`/metadata para o usuário localizar no original (rastreabilidade).[^2]


### 4.6 Geração de saída

**PDF**

- Converter elementos traduzidos → HTML (com CSS básico) → PDF (playwright/WeasyPrint).
- PDF final deve conter paginação, cabeçalho opcional “Traduzido por …” e metadados (idiomas).

**EPUB**

- Gerar capítulos (por título/parent_id quando disponível) e empacotar com `ebooklib` (ou HTML + zip EPUB).
- Minimizar dependência de layout original; foco em leitura.[^2]


### 4.7 Status e download

- Endpoint `GET /jobs/{id}` retorna progresso (ex.: elementos processados / total, etapa atual).
- Endpoint `GET /jobs/{id}/download?format=pdf|epub` retorna arquivo final.

***

## 5) Requisitos não funcionais

- **Escalabilidade**: jobs longos; workers paralelos; retentativas por elemento.
- **Resiliência**: retomar job após falha (checkpoint).
- **Observabilidade**: logs estruturados + métricas por etapa (extração, OCR, tradução, render).
- **Segurança**: limitar tamanho; AV scan opcional; isolamento de execução (container).

***

## 6) Arquitetura (Python-only)

### 6.1 Componentes

- API: **FastAPI** (upload, status, download).
- Fila: **Celery + Redis** (ou RQ/Arq) para jobs assíncronos.
- Storage: S3 compatível (MinIO/R2/S3) para PDF original e outputs.
- Banco: Postgres para `jobs`, `elements`, `translations`.


### 6.2 Pipeline (etapas)

1) `ingest`: salva PDF, cria job.
2) `partition`: `partition_pdf(strategy=...)` → lista de elements com `element_id` e metadata.[^1][^2]
3) `translate_elements`: traduz cada element; salva incrementalmente.
4) `render_pdf` e/ou `render_epub`.
5) `finalize`: marca job como concluído e disponibiliza downloads.

***

## 7) Pacotes/ferramentas recomendadas (Python)

### Extração/estrutura

- `unstructured` (core do parsing) e extras para PDF/OCR conforme necessário.[^3][^1]
- (Opcional fallback) `pdfminer.six` para PDFs simples quando você quiser um modo ultra-rápido de texto bruto (sem layout avançado).[^8][^9]


### Render

- `playwright` ou `weasyprint` para HTML→PDF (escolha depende do seu ambiente/infra).
- `ebooklib` para EPUB.


### Infra

- `fastapi`, `uvicorn`
- `celery`, `redis`
- `sqlalchemy` + `alembic` (ou `sqlmodel`)

***

## 8) Modelo de dados (mínimo)

**jobs**

- `id`, `status`, `source_lang`, `target_lang`, `strategy`, `output_formats`, `created_at`, `finished_at`, `error`

**elements**

- `job_id`, `element_id`, `type`, `text`, `metadata_json`, `order_index`, `page_number` (derivado)

**translations**

- `job_id`, `element_id`, `source_text`, `translated_text`, `status`, `model`, `prompt_version`, `retry_count`

O `element_id` do Unstructured é determinístico por padrão (hash com texto + posição + página + arquivo) e pode virar UUID com `unique_element_ids=True`, o que facilita PK e dedupe.[^5][^2]

***

## 9) UX e limites (MVP)

- Limite padrão de upload (ex.: 200–500MB) e páginas (ex.: 1.000) configuráveis.
- Progresso por etapa e ETA aproximado (baseado em elementos por minuto).
- Mensagens claras quando o PDF exigir OCR (mais lento/caro) usando `ocr_only`/`hi_res`.[^3][^1]

***

## 10) Critérios de aceitação

- Upload de um PDF de 700 páginas cria job e conclui sem timeout (processo assíncrono).
- Saída PDF abre corretamente e contém o texto traduzido na ordem correta na maioria dos casos.[^1]
- O sistema consegue reprocessar somente elementos com falha (retry) sem reiniciar tudo, usando `element_id` + status persistido.[^2]

***

## 11) Plano de execução (MVP em 2–3 semanas)

1) Semana 1: API + storage + job queue + `partition_pdf` com estratégias + persistência de elementos.[^1]
2) Semana 2: tradução por elemento + retry + validações heurísticas + geração HTML.[^2]
3) Semana 3: render PDF/EPUB + progresso + hardening (limites, logs, métricas).

***

Se você quiser, eu também posso:

- Definir os **prompts padrão** (tradução, tabela, títulos, “não inventar”) e o schema JSON interno por elemento (para você manter estável).
- Propor uma estratégia “auto → fallback hi_res/ocr_only” com detecção de qualidade do texto extraído usando os próprios metadados/elementos do Unstructured.[^3][^1]
<span style="display:none">[^10][^11][^12][^13][^14][^15][^16]</span>

<div align="center">⁂</div>

[^1]: https://docs.unstructured.io/open-source/core-functionality/partitioning

[^2]: https://docs.unstructured.io/open-source/concepts/document-elements

[^3]: https://docs.unstructured.io/open-source/concepts/partitioning-strategies

[^4]: https://github.com/Unstructured-IO/unstructured/blob/main/unstructured/partition/pdf.py

[^5]: https://docs.unstructured.io/api-reference/legacy-api/partition/api-parameters

[^6]: https://stackoverflow.com/questions/49722754/keep-layout-of-extracted-text-in-pdfminer-six-python

[^7]: https://docs.unstructured.io/ui/document-elements

[^8]: https://github.com/pdfminer/pdfminer.six/blob/master/docs/source/tutorial/highlevel.rst

[^9]: https://pdfminersix.readthedocs.io/en/latest/tutorial/highlevel.html

[^10]: https://unstructured.readthedocs.io/en/main/best_practices/strategies.html

[^11]: https://unstructured.readthedocs.io/en/main/ingest/configs/partition_config.html

[^12]: https://unstructured-53.mintlify.app/api-reference/partition/document-elements

[^13]: https://blog.csdn.net/engchina/article/details/143256606

[^14]: https://pdfminersix.readthedocs.io/en/latest/reference/highlevel.html

[^15]: https://deepwiki.com/Unstructured-IO/unstructured/2.1-partitioning-strategies

[^16]: https://github.com/pdfminer/pdfminer.six/blob/master/docs/source/tutorial/extract_pages.rst

