# Image Inspector

Aplicativo desktop para inspecao visual operacional com cameras Basler e modelos YOLO.

Este projeto e uma versao enxuta do toolkit USSEEWA, voltada para usuario final/cliente. O foco e operacao robusta, usabilidade e coleta organizada de dados para realimentar treinamentos futuros.

## Fluxo Principal

1. Conectar camera Basler.
2. Selecionar perfil `.pfs`, quando necessario.
3. Selecionar modelos `.pt`.
4. Executar inspecao simples ou hibrida com um clique.
5. Revisar o resultado visual.
6. Salvar manualmente como `verdadeiro_positivo`, `verdadeiro_negativo`, `falso_positivo` ou `falso_negativo`.
7. Usar a aba **Criar dataset** para capturar imagens rotuladas manualmente.

## Estrutura

```text
image_inspector/
  app.py
  config.py
  core/
    basler_camera.py
    yolo_models.py
    inspection.py
    storage.py
  ui/
    main_window.py
    threads.py
models/
  inspection/
  detection/
  classification/
profiles/
data/
  inspections/
logs/
packaging/
  image_inspector.spec
  build_exe.ps1
  install_client.ps1
```

## Executar em desenvolvimento

```powershell
venv\Scripts\python.exe -m image_inspector.app
```

## Gerar executavel

No computador de build:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build_exe.ps1 -Clean
```

A saida sera criada em:

```text
dist/Image Inspector/Image Inspector.exe
```

As pastas `models`, `profiles`, `data` e `logs` ficam ao lado do executavel para permitir trocar `.pt` e `.pfs` sem recompilar.

## Instalar no computador do cliente

1. Copie a pasta `dist` inteira para o computador do cliente.
2. Abra PowerShell como Administrador dentro da pasta `dist`.
3. Execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_client.ps1
```

O instalador copia o aplicativo para:

```text
C:\Program Files\Image Inspector
```

E cria atalhos em:

```text
Area de Trabalho
Menu Iniciar > Image Inspector
```

## Onde colocar modelos e perfis no cliente

Os modelos `.pt` fornecidos com o pacote podem ficar ao lado do executavel. Modelos importados pelo aplicativo sao guardados na pasta de dados do usuario:

```text
%LOCALAPPDATA%\Image Inspector\models\inspection\       # .pt importados para inspecao
%LOCALAPPDATA%\Image Inspector\models\detection\         # .pt de deteccao hibrida
%LOCALAPPDATA%\Image Inspector\models\classification\    # .pt de classificacao hibrida
%LOCALAPPDATA%\Image Inspector\profiles\                 # .pfs Basler adicionados pelo usuario
```

## Organizacao dos Dados

Cada revisao manual cria uma pasta em:

```text
%LOCALAPPDATA%/Image Inspector/data/inspections/YYYY-MM-DD/<classe_de_revisao>/HHMMSS_microsegundos/
```

Dentro dela ficam a foto original, uma anotacao por categoria de modelo selecionada e `metadata.json`.
Na tela de revisao, o operador informa se existe defeito; o aplicativo calcula automaticamente verdadeiro positivo, verdadeiro negativo, falso positivo ou falso negativo a partir do resultado dos modelos.

No Windows, imagens, configuracoes e logs ficam em `%LOCALAPPDATA%\Image Inspector\`, uma pasta gravavel pelo usuario mesmo quando o aplicativo esta instalado em `C:\Program Files`.
Modelos e perfis distribuidos ao lado do executavel continuam disponiveis como leitura. A categoria confirmada e registrada nos nomes dos arquivos, no `metadata.json` e no indice diario; a foto e guardada uma unica vez.
As imagens de referencia ficam em `%LOCALAPPDATA%\Image Inspector\models\inspection\<categoria>\reference.png`.

Na aba **Criar dataset**, o operador seleciona uma categoria, acompanha a câmera ao vivo e captura imagens rotuladas sem executar inferência. Categorias, referências, capturas e metadados ficam separados das revisões de inspeção em `%LOCALAPPDATA%/Image Inspector/data/dataset/`. Cada foto recebe um `.json` com categoria, operador, serial da câmera e horário. Categorias podem ser alteradas sem apagar as fotos já capturadas; a imagem de referência cria `<categoria>_example.txt` na pasta da categoria. **Enviar / Exportar** registra as capturas em `export_queue.jsonl` para um sincronizador externo. A lista inicial segue a configuração ABAPA: `mancha`, `rasgo` e `contaminacao`.

## Problemas com PyInstaller

Se o build falhar com EndUpdateResourceW ou bloqueio de antivirus, veja packaging/PLANOS_EMPACOTAMENTO.md.


## Melhorias Operacionais Ativas

A versao atual inclui recursos para operacao mais repetivel:

- cache de modelos YOLO carregados, evitando recarregar `.pt` a cada inspecao;
- logs persistentes em `logs/system.log` e `logs/errors.log`;
- configuracao persistente em `config/runtime_settings.json`;
- registro de operador, camera, serial, perfil `.pfs`, modelos, hashes SHA-256 e thresholds no `metadata.json`;
- indice diario em `data/inspections/YYYY-MM-DD/index.csv`;
- botoes de revisao em linguagem operacional, mantendo VP/VN/FP/FN internamente;
- status basico de camera, perfil e modelos na tela principal.
