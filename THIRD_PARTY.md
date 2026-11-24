# Third-party components
- Portable Python: official CPython 3.13.16 Windows x64 embeddable package, https://www.python.org/downloads/release/python-31316/. License included at `runtime/python/LICENSE.txt`; original archive SHA-256 in `vendor/MANIFEST.json`. Only its relative module search paths are configured for this application.
- Agency logo: user-supplied `행정안전부-mi.zip`, entry `행정안전부_국_좌우.jpg`, stored unchanged as `assets/mois-logo.jpg`. Agency branding is not covered by the source-code or font license; no official-site certification claim is made.
- UI font: Noto Sans KR Hestia (Regular, Medium, Bold), received unchanged from MOIS's public font assets. Upstream: https://github.com/theeluwin/NotoSansKR-Hestia (Apache-2.0, Copyright 2020 theeluwin). License: assets/fonts/LICENSE-Hestia.txt. Source URLs and checksums: assets/README.md. No government certification marks or news photographs are included.
- Department embedding: https://huggingface.co/dragonkue/snowflake-arctic-embed-l-v2.0-ko (Apache-2.0). Downloaded separately, not included in the source ZIP.
- Converter source: https://github.com/neolord0/hwp2hwpx
  Commit edc05278506b663d5bdd98050a51f54b7ff5e0bc, Apache-2.0.
  Source copied unchanged except a new ConvertMain.java entrypoint and replacement build POM.
  License: tools/converter/LICENSE-upstream.txt.
- hwplib 1.1.10 and hwpxlib 1.0.9: kr.dogfoot Maven artifacts, Apache-2.0.
- Model downloaded separately: https://huggingface.co/mykor/A.X-4.0-Light-gguf
  Original: https://huggingface.co/skt/A.X-4.0-Light (Apache-2.0).
- llama-cpp-python installation: https://llama-cpp-python.readthedocs.io/en/latest/
- Python dependencies retain their respective licenses in installed distributions.
