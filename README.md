# ForensicCloud

A forensic point cloud cleaning platform for processing E57 scan files. Upload a scan, remove noise and artefacts with configurable algorithms, view results in real-time 3D, and export a cleaned E57 with a full audit report.

## Features

- **Upload** — streams large E57 files without loading them fully into memory
- **Cleaning algorithms**
  - Statistical Outlier Removal (SOR) — removes isolated points by k-nearest-neighbour distance statistics
  - Radius Outlier Removal (ROR) — removes points with too few neighbours within a fixed radius
  - Color Filter — removes forensic markers (yellow tape, orange cones, red tape) by HSV hue range
  - Plane RANSAC — detects and removes large planar surfaces such as glass walls and windows
  - Manual Region Deletion — delete all points inside a user-drawn bounding box
- **3D Viewer** — WebGL renderer (Three.js) with up to 2 million preview points, supports orbit/pan/zoom
- **Audit log** — every operation is recorded with parameters, point counts, and timestamps
- **PDF report** — one-click forensic report export with operation history and scan metadata
- **GPU acceleration** — all algorithms accelerated via CuPy/CUDA when an NVIDIA GPU is available, with automatic CPU-parallel fallback (scikit-learn, multiprocessing)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Uvicorn |
| Algorithms | NumPy, SciPy, scikit-learn, CuPy (optional) |
| Point cloud I/O | pye57 |
| Frontend | React 18, TypeScript, Vite |
| 3D visualization | Three.js |
| Styling | Tailwind CSS |
| Reports | ReportLab |

---

## Option A — Docker (recommended)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) with the Compose plugin.  
For GPU support, also install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

```bash
git clone <repo-url>
cd ForensicCloud
docker compose up --build
```

Open **http://localhost:8000** in your browser.

Session files are stored in a named Docker volume (`sessions`) and persist across restarts.

### GPU behaviour

On first startup the entrypoint script runs automatically:

1. Checks whether `nvidia-smi` is accessible (requires `--gpus all`, which Compose sets via the `deploy` block).
2. If a GPU is found, checks whether `cupy-cuda12x` is installed.
3. If not installed, installs it (~200 MB, one-time per container). `cupy-cuda12x` bundles its own CUDA 12.x runtime, so no CUDA base image is needed.
4. If no GPU is found, the server starts in CPU-parallel mode.

To run without GPU support, remove the `deploy` block from `docker-compose.yml` before building, or simply use:

```bash
docker build -t forensiccloud .
docker run -p 8000:8000 forensiccloud
```

### Useful commands

```bash
# View logs
docker compose logs -f

# Stop
docker compose down

# Rebuild after code changes
docker compose up --build

# Check GPU acceleration status
curl http://localhost:8000/api/gpu-info
```

---

## Option B — Local (Windows)

**Prerequisites**

| Requirement | Version | Download |
|-------------|---------|---------|
| Python | 3.11 | [python.org](https://www.python.org/downloads/) |
| Node.js | 20 LTS | [nodejs.org](https://nodejs.org/) |
| NVIDIA GPU + CUDA 12.x | optional | [developer.nvidia.com](https://developer.nvidia.com/cuda-downloads) |

**Install**

```bat
install.bat
```

This creates a Python virtual environment, installs all dependencies, and builds the frontend. Run once; re-run only when dependencies change.

**Enable GPU acceleration (optional)**

After running `install.bat`, uncomment the cupy line in `backend/requirements.txt` and reinstall:

```bat
cd backend
.venv\Scripts\activate.bat
pip install cupy-cuda12x>=13.0.0
```

**Start**

```bat
start.bat
```

Opens the app at **http://localhost:8000**.

**Development mode** (hot-reload for both backend and frontend):

```bat
start_dev.bat
```

Runs the FastAPI backend on port 8000 and the Vite dev server on port 5173.

---

## Configuration

All settings are controlled via environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `FORENSICCLOUD_WORK_DIR` | system temp dir | Directory for session scratch files |
| `HOST` | `127.0.0.1` | Server bind address (`0.0.0.0` for Docker/remote) |
| `PORT` | `8000` | Server port |
| `OPEN_BROWSER` | `1` | Set to `0` to skip opening a browser tab on startup |

---

## API

The REST API is available at `http://localhost:8000/api`.  
Interactive docs: **http://localhost:8000/api/docs**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/gpu-info` | GPU/acceleration status |
| `POST` | `/api/upload/{session_id}` | Upload an E57 file |
| `POST` | `/api/process/auto/{session_id}` | Run the full auto-clean pipeline |
| `POST` | `/api/process/manual/{session_id}` | Run a single algorithm |
| `GET` | `/api/process/status/{session_id}` | Poll processing progress |
| `GET` | `/api/process/preview/{session_id}/{version}` | Stream binary preview |
| `GET` | `/api/export/{session_id}` | Download cleaned E57 |
| `GET` | `/api/audit/{session_id}/log` | Audit log entries |
| `GET` | `/api/audit/{session_id}/report` | Download PDF report |

---

## Project Structure

```
ForensicCloud/
├── backend/
│   ├── main.py               # FastAPI app, server entry point
│   ├── config.py             # Paths and constants
│   ├── requirements.txt
│   ├── routers/
│   │   ├── upload.py         # E57 upload and parsing
│   │   ├── process.py        # Algorithm dispatch
│   │   ├── export.py         # E57 export
│   │   └── audit.py          # Audit log and PDF report
│   └── services/
│       ├── gpu_utils.py      # GPU/CPU hardware probe
│       ├── noise_removal.py  # All cleaning algorithms
│       ├── e57_handler.py    # E57 read/write, voxel downsampling
│       ├── session_manager.py
│       ├── audit_logger.py
│       └── pdf_generator.py
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/       # Viewer3D, ToolPanel, FileUpload, …
│   │   ├── api/client.ts
│   │   └── types/index.ts
│   ├── package.json
│   └── vite.config.ts
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
└── install.bat / start.bat   # Windows shortcuts
```
