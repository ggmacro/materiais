# Publicar o Laboratorio de Materiais na nuvem

Este projeto ja esta preparado para rodar em plataformas que aceitam apps Python
com `Procfile` ou comando de inicializacao.

## Opcao simples: Render

1. Crie uma conta no Render.
2. Coloque este projeto em um repositorio no GitHub.
3. No Render, escolha "New Web Service".
4. Conecte o repositorio.
5. Use estes comandos:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python app.py`
6. Publique o servico.

O Render define automaticamente a variavel `PORT`, e o arquivo `app.py` ja usa
essa porta.

## Opcao simples: Railway

1. Crie uma conta no Railway.
2. Escolha "Deploy from GitHub repo".
3. Selecione este projeto.
4. Use o comando de start: `python app.py`.

## Variaveis opcionais

Para ativar consultas na Materials Project API:

```text
MP_API_KEY=sua_chave
```

Sem essa chave, o app continua funcionando com a base local e com buscas de
artigos via OpenAlex/Crossref.

## Teste local antes de publicar

```powershell
python app.py
```

Depois abra:

```text
http://127.0.0.1:8000
```
