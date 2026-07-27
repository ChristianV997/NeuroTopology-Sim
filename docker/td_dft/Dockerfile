FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential gfortran cmake pkg-config \
       libopenblas-dev liblapack-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt /tmp/requirements-base.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir \
       numpy scipy h5py biopython pyscf==2.7.0

COPY scripts/run_tddft.py /workspace/run_tddft.py

ENTRYPOINT ["python", "/workspace/run_tddft.py"]
