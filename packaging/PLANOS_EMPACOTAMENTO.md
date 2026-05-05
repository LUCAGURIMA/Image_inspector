# Planos Alternativos de Empacotamento

O erro `EndUpdateResourceW` acontece na fase em que o PyInstaller tenta alterar recursos internos do `.exe`. Se o computador tiver antivirus/EDR corporativo bloqueando essa operacao, o problema pode persistir mesmo com venv limpa.

## Plano A - PyInstaller em maquina liberada

Use este plano quando houver uma maquina sem bloqueio corporativo ou com exclusao de `build/` e `dist/` liberada pela TI.

```powershell
cd "C:\Users\adm_luca.goulart\Desktop\Abapa"
python -m venv venv_build
.\venv_build\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r .\packaging\requirements-client.txt
powershell -ExecutionPolicy Bypass -File .\packaging\build_exe.ps1 -Clean
```

Saida esperada:

```text
dist/Image Inspector/Image Inspector.exe
```

## Plano B - Pacote portatil sem PyInstaller

Use este plano quando o PyInstaller for bloqueado. Ele nao cria um `.exe` unico; cria uma pasta com runtime Python e um launcher clicavel `.vbs`/`.cmd`.

```powershell
cd "C:\Users\adm_luca.goulart\Desktop\Abapa"
python -m venv venv_build
.\venv_build\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r .\packaging\requirements-client.txt
powershell -ExecutionPolicy Bypass -File .\packaging\build_portable.ps1 -Clean
```

Saida:

```text
dist_portable/Image Inspector/
```

Teste local:

```powershell
& ".\dist_portable\Image Inspector\Image Inspector.cmd"
```

Instalacao no cliente:

```powershell
cd "CAMINHO\dist_portable\Image Inspector"
powershell -ExecutionPolicy Bypass -File .\install_portable_client.ps1
```

Observacao: este plano e mais simples, mas depende de o runtime copiado funcionar no computador do cliente. Teste em uma maquina limpa antes de entregar.

## Plano C - Instalador corporativo com Python aprovado

Use quando a TI nao permitir executavel gerado por PyInstaller.

1. Instalar Python 3.11 aprovado pela TI no cliente.
2. Copiar o projeto Image Inspector para `C:\Program Files\Image Inspector`.
3. Criar uma venv local nessa pasta.
4. Instalar dependencias com `requirements-client.txt`.
5. Criar atalho chamando:

```text
pythonw.exe -m image_inspector.app
```

Este plano e menos elegante, mas costuma passar em ambientes corporativos porque nao usa bootloader empacotado.

## Plano D - Versao ONNX sem Torch/PyInstaller pesado

Para produto final, este e o caminho mais robusto.

1. Exportar modelos YOLO para ONNX no toolkit de treino.
2. Trocar a inferencia do Image Inspector para `onnxruntime` ou OpenCV DNN.
3. Remover `torch`, `torchvision` e `ultralytics` do runtime do cliente.
4. Gerar executavel muito menor e com menos chance de bloqueio.

Beneficios:

- build mais rapido;
- instalador menor;
- menos DLLs CUDA/Torch;
- menor chance de bloqueio por antivirus;
- melhor previsibilidade em maquinas de cliente.

Este plano exige uma pequena refatoracao no `image_inspector/core/yolo_models.py`, mas e o melhor para distribuicao comercial.
