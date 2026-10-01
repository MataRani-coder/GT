# TensorBoard dependency fix

The AI tracker was failing during startup with:

```text
Import failure: No module named 'tensorboard'
```

`torchreid` imports TensorBoard components during initialization. The project now explicitly declares `tensorboard>=2.14.0` in `requirements.txt` and the Windows launcher checks for it before starting Ghost Trail.

Run `setup_and_run.bat` again so the dependency is installed.
