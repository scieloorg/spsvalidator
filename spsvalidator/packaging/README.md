# Packaging

## macOS

Gera bundle em `dist/`

```console
bash packaging/build_macos.sh
```

## Linux

Gera binário em `dist/` para converter em AppImage

```console
bash packaging/build_linux.sh
```

## Windows

Gera `.exe` em `dist/`.


```console
powershell -ExecutionPolicy Bypass -File packaging/build_windows.ps1
```
