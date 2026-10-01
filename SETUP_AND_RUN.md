# Ghost Trail — One-Click Windows Setup

## Requirements

Install these once on the Windows machine:

- Python 3.10+
- Node.js LTS (includes npm)
- A working webcam if using the live camera

## Start Ghost Trail

Double-click:

`setup_and_run.bat`

The script will:

1. Check Python and npm.
2. Install the Python dependencies from `requirements.txt`.
3. Run `npm ci` in `dashboard/` using the committed lockfile.
4. Build the React dashboard with `npm run build`.
5. Start FastAPI on `http://127.0.0.1:8765`.
6. Open the dashboard in the default browser.

## If npm installation fails

Open Command Prompt in `dashboard/` and run:

```bat
npm cache clean --force
npm config set registry https://registry.npmjs.org/
npm ci
```

Then return to the project root and run `setup_and_run.bat` again.

## If the camera does not open

Run:

```bat
python test_camera.py
```

The camera diagnostic reports the working camera index and backend.

## Stopping the application

Close the `Ghost Trail Server` command window, or press `Ctrl+C` in it.

## Important

The script does not install `node_modules` into the ZIP. Dependencies are installed locally on the machine, keeping the project portable and avoiding a huge platform-specific archive.
