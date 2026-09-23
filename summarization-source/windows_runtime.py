"""Run lawtool with Windows CUDA DLL paths and dependency preload."""
from pathlib import Path
import ctypes
import importlib.metadata as metadata
import os
import runpy
import sys

DLL_DIRECTORIES = []
DLL_HANDLES = []


def prepare_windows_dlls():
    if os.name != 'nt':
        return
    dist = metadata.distribution('llama-cpp-python')
    lib = Path(dist.locate_file('llama_cpp/lib')).resolve()
    paths = [lib]
    binaries = {}
    for package in ('nvidia-cuda-runtime-cu12', 'nvidia-cublas-cu12'):
        dep = metadata.distribution(package)
        for entry in dep.files or []:
            if str(entry).lower().endswith('.dll'):
                p = Path(dep.locate_file(entry)).resolve()
                if p.is_file():
                    binaries[p.name.lower()] = p
                    if p.parent not in paths:
                        paths.append(p.parent)
    for directory in paths:
        DLL_DIRECTORIES.append(os.add_dll_directory(str(directory)))
    # Process-local PATH also supports loaders that use legacy search flags.
    os.environ['PATH'] = os.pathsep.join(str(p) for p in paths) + os.pathsep + os.environ.get('PATH', '')
    for name in ('cudart64_12.dll', 'cublasLt64_12.dll', 'cublas64_12.dll'):
        p = binaries.get(name.lower())
        if p is None:
            raise FileNotFoundError('Missing CUDA DLL: ' + name)
        DLL_HANDLES.append(ctypes.WinDLL(str(p)))
        print('Loaded:', name, flush=True)
    for name in ('ggml-base.dll', 'ggml-cpu.dll', 'ggml-cuda.dll', 'ggml.dll', 'llama.dll'):
        p = lib / name
        if not p.is_file():
            raise FileNotFoundError('Missing llama DLL: ' + str(p))
        DLL_HANDLES.append(ctypes.WinDLL(str(p)))
        print('Loaded:', name, flush=True)

