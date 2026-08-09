# CaptaEditais

Radar institucional de editais e chamadas públicas (FAPEMIG, CNPq) e de TEDs
(Transferegov), com triagem automática de elegibilidade.

- `index.html` — a aplicação (abre direto pelo GitHub Pages)
- `data/editais.json` — base de editais, atualizada automaticamente pelo scraper
- `scraper/` — código Python que raspa FAPEMIG e CNPq
- `.github/workflows/scrape-editais.yml` — roda o scraper 1x/dia sozinho

Detalhes técnicos do scraper (como funciona, como rodar localmente, o que
ajustar se algo quebrar): veja [`README-scraper.md`](./README-scraper.md).

## Publicar no GitHub — passo a passo

### 1. Criar o repositório e subir os arquivos

Se você **ainda não tem** um repositório:

```bash
cd captaeditais              # a pasta com estes arquivos
git init
git add .
git commit -m "Primeira versão do CaptaEditais"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git
git push -u origin main
```

Se você **já tem um repositório**, copie o conteúdo desta pasta pra dentro
dele (mantendo a estrutura de pastas `data/`, `scraper/`, `.github/`) e faça
o commit normalmente.

### 2. Ativar o GitHub Pages

No repositório, vá em **Settings → Pages**:
- Em "Source", escolha **Deploy from a branch**
- Branch: **main**, pasta: **/ (root)**
- Salve

Em alguns minutos o site fica disponível em:
`https://SEU_USUARIO.github.io/SEU_REPO/`

(O GitHub Pages procura por `index.html` na raiz automaticamente — por isso
o arquivo se chama `index.html`, não `captaeditais.html`.)

### 3. Ativar o scraper automático

O workflow em `.github/workflows/scrape-editais.yml` já vem pronto e **não
precisa de nenhuma configuração extra** — ele usa o token automático do
GitHub Actions (`GITHUB_TOKEN`) pra commitar o `data/editais.json`
atualizado. Só confirme que ficou habilitado:

- Vá em **Settings → Actions → General**
- Em "Workflow permissions", marque **Read and write permissions**
  (necessário pra ele conseguir commitar o JSON de volta no repositório)
- Salve

Depois disso:
- Ele roda sozinho todo dia às 06h UTC (~03h em Brasília), **ou**
- Você pode disparar manualmente: aba **Actions** → selecione
  "Atualizar editais (scraper)" → botão **Run workflow**

### 4. Testar antes de subir (opcional, mas recomendado)

```bash
pip install -r scraper/requirements.txt
playwright install chromium
python scraper/run.py          # gera/atualiza data/editais.json
python -m http.server 8000     # serve localmente
# abra http://localhost:8000/index.html
```

## Estrutura completa

```
.
├── index.html                          <- app (GitHub Pages serve este)
├── captaeditais.html                   <- cópia idêntica (nome antigo, opcional manter)
├── data/
│   └── editais.json                    <- gerado pelo scraper (já vem com exemplo)
├── scraper/
│   ├── scrape_cnpq.py
│   ├── scrape_fapemig.py
│   ├── normalize.py
│   ├── run.py
│   └── requirements.txt
├── .github/workflows/
│   └── scrape-editais.yml
├── .gitignore
├── README.md                           <- este arquivo
└── README-scraper.md                   <- detalhes técnicos do scraper
```

> Se preferir não manter os dois HTMLs duplicados, pode apagar
> `captaeditais.html` e ficar só com `index.html` — são idênticos.
