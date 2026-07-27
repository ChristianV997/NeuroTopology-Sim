FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 MPLBACKEND=Agg OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
RUN python -m pip install --no-cache-dir --upgrade pip && python -m pip install --no-cache-dir numpy scipy mne ripser scikit-learn matplotlib
COPY scripts /workspace/scripts
COPY physics /workspace/physics
ENTRYPOINT ["python", "/workspace/scripts/eeg_topology_ds005620.py"]
