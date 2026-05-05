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

Depois de instalado:

```text
C:\Program Files\Image Inspector\models\inspection\       # .pt para inspecao simples
C:\Program Files\Image Inspector\models\detection\         # .pt de deteccao hibrida
C:\Program Files\Image Inspector\models\classification\    # .pt de classificacao hibrida
C:\Program Files\Image Inspector\profiles\                 # .pfs Basler
```

## Organizacao dos Dados

Cada revisao manual cria uma pasta em:

```text
data/inspections/YYYY-MM-DD/<classe_de_revisao>/HHMMSS_microsegundos/
```

Dentro dela ficam `original.jpg`, `annotated.jpg` e `metadata.json`.

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
