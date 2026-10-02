# Image Inspector

Aplicativo desktop para inspeção visual com câmeras Basler e modelos YOLO. A interface reúne operação, configuração da câmera e modelos, confirmação dos resultados e coleta manual de imagens para datasets.

## Abas do aplicativo

### Operação

1. Selecione uma ou mais categorias de inspeção. A mesma foto é analisada sequencialmente por cada modelo selecionado.
2. Capture uma imagem pela câmera Basler ou reanalise a imagem atual.
3. Confira o resultado e, quando houver mais de uma categoria, escolha qual imagem anotada visualizar.
4. Confirme se o produto tem defeito ou está conforme. Em seguida, marque as categorias de defeito pertinentes e salve a revisão.

As revisões são classificadas automaticamente como verdadeiro positivo, verdadeiro negativo, falso positivo ou falso negativo. As categorias informadas ficam nos metadados e nos nomes dos arquivos; cada foto original é guardada uma vez.

### Configuração

- Selecione e conecte uma câmera Basler.
- Selecione o perfil `.pfs` da câmera.
- Importe arquivos `.pt` ou selecione os modelos de inspeção, detecção e classificação.
- Ajuste a confiança mínima quando necessário.

Os modelos de inspeção aparecem como cartões com imagem de referência. É possível adicionar ou trocar a imagem de cada categoria. A seleção múltipla é usada pela aba Operação.

### Criar dataset

Esta aba reproduz o fluxo do coletor ABAPA dentro do Image Inspector. Ela usa a câmera e o perfil selecionados em Configuração, mostra a visualização ao vivo e permite capturar imagens manualmente, sem executar inferência.

1. Informe o operador, se desejar.
2. Toque em uma categoria para selecioná-la; a borda azul indica a seleção.
3. Use **+ CATEGORIA** para criar uma categoria ou **REMOVER** para tirá-la da lista.
4. Use **ADICIONAR / TROCAR IMAGEM** para escolher uma imagem de referência para a categoria selecionada.
5. Toque em **TIRAR FOTO**. A imagem é salva na pasta da categoria com um arquivo JSON de metadados.
6. Use **ENVIAR / EXPORTAR** para adicionar as imagens capturadas na sessão à fila de exportação.

Remover uma categoria da lista não apaga sua pasta nem as imagens existentes. As categorias iniciais são `mancha`, `rasgo` e `contaminacao`; elas podem ser alteradas na própria aba. A imagem de referência é copiada para a pasta da categoria e o arquivo `<categoria>_example.txt` registra o caminho usado pelo cartão.

## Dados e arquivos

No Windows, modelos importados, perfis, imagens, configurações e logs ficam em `%LOCALAPPDATA%\Image Inspector\`. No Linux, a pasta padrão é `~/.local/share/Image Inspector/` (ou `$XDG_DATA_HOME/Image Inspector/`, se definida).

```text
Image Inspector/
  models/
    inspection/                 # modelos de inspeção importados e referências
    detection/                  # modelos de detecção
    classification/             # modelos de classificação
  profiles/                     # perfis .pfs adicionados pelo usuário
  config/runtime_settings.json  # modelos, câmera, operador e zoom do painel
  data/
    inspections/<data>/<classe>/# revisões manuais da aba Operação
    dataset/
      categories.json           # categorias e pastas do dataset
      captures/<categoria>/     # imagens, referências e metadados JSON
      export_queue.jsonl        # fila para sincronização externa
  logs/
```

Uma captura do dataset segue o padrão `<categoria>_AAAAmmdd_HHMMSS_<serial>.jpg` e recebe um JSON com categoria, operador, serial e horário. Se já existir uma imagem com o mesmo nome, o aplicativo acrescenta frações de segundo para evitar sobrescrevê-la. A imagem de referência fica na pasta da categoria; o `.txt` ao lado aponta para ela.

Uma revisão da aba Operação guarda a foto original, as imagens anotadas por categoria de modelo e `metadata.json`. As categorias de inspeção e as categorias do dataset têm configurações separadas para evitar misturar esses dados.

`export_queue.jsonl` apenas registra os caminhos das capturas da sessão para que um sincronizador externo possa processá-las. O aplicativo não envia imagens pela rede.

## Estrutura do código

```text
image_inspector/
  app.py
  config.py
  core/
    basler_camera.py
    dataset_collection.py
    inspection.py
    runtime.py
    storage.py
    yolo_models.py
  ui/
    dataset_tab.py
    main_window.py
    threads.py
```

## Executar em desenvolvimento

Com o ambiente virtual e as dependências do projeto instalados:

```powershell
venv\Scripts\python.exe -m image_inspector.app
```

## Gerar o executável

No computador de build, execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build_exe.ps1 -Clean
```

A saída será criada em:

```text
dist/Image Inspector/Image Inspector.exe
```

## Instalar no computador do cliente

1. Copie a pasta `dist` inteira para o computador do cliente.
2. Abra o PowerShell como Administrador dentro da pasta `dist`.
3. Execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_client.ps1
```

O instalador copia o aplicativo para `C:\Program Files\Image Inspector` e cria atalhos na Área de Trabalho e no Menu Iniciar. A pasta de dados do usuário continua gravável sem privilégios de administrador.

## Modelos e perfis distribuídos

Modelos `.pt` e perfis `.pfs` distribuídos com o pacote podem ficar junto do executável, nas pastas `models/` e `profiles/`. Arquivos importados pelo aplicativo são copiados para as pastas de dados do usuário. Isso permite atualizar modelos e perfis sem recompilar o executável.

## Problemas com PyInstaller

Se o build falhar com `EndUpdateResourceW` ou bloqueio de antivírus, consulte [packaging/PLANOS_EMPACOTAMENTO.md](packaging/PLANOS_EMPACOTAMENTO.md).
