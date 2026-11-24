"""Build the bundled HWP converter on cloud hosts, without uploading documents."""
import os
from pathlib import Path
import shutil
import subprocess
from threading import Lock

ROOT=Path(__file__).resolve().parents[1]
_BUILD_LOCK=Lock()


def ensure_converter(jar):
    jar=Path(jar)
    if jar.is_file():
        return
    if os.environ.get('LAWTOOL_AUTO_BUILD_CONVERTER')!='1':
        raise ValueError('HWP 변환 JAR 없음: python tools/build_converter.py 실행 필요')
    expected=ROOT/'tools/converter/target/hwp-converter.jar'
    if jar.resolve()!=expected.resolve():
        raise ValueError('자동 빌드는 프로젝트에 포함된 HWP 변환기 경로만 지원합니다.')
    with _BUILD_LOCK:
        if jar.is_file():
            return
        maven=shutil.which('mvn')
        if not maven or not shutil.which('java'):
            raise ValueError('서버의 Java/Maven이 없습니다. packages.txt 설치 상태를 확인하세요.')
        try:
            result=subprocess.run(
                [maven,'-B','-ntp','-f',str(ROOT/'tools/converter/pom.xml'),
                 'package','-DskipTests'],cwd=ROOT,capture_output=True,timeout=300,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError('HWP 변환기 준비 시간이 초과되었습니다. 서버 로그와 Maven 연결을 확인하세요.') from error
        if result.returncode or not jar.is_file():
            # Build logs contain no source documents or user credentials.
            print('HWP converter build failed:',result.stderr.decode('utf-8',errors='replace')[-1500:])
            raise ValueError('HWP 변환기 준비에 실패했습니다. 서버 로그와 Maven 연결을 확인하세요.')
