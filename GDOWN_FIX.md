# gdown startup fix

The AI tracker imports `torchreid`, whose pretrained OSNet loader requires the `gdown` package when it downloads pretrained weights from Google Drive.

The previous requirements file omitted `gdown`, causing:

`Import failure: No module named 'gdown'`

This build adds:

```text
gdown>=5.2.0
```

The Windows setup script also verifies that `gdown` is importable before starting Ghost Trail.

After replacing the project, run:

```powershell
.\setup_and_run.bat
```

If the model download itself is blocked by a network/firewall, the console will show the actual download error rather than the misleading missing-module error.
