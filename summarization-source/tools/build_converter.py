from pathlib import Path
import shutil, subprocess, urllib.request, zipfile
root=Path(__file__).resolve().parents[1]
mvn=shutil.which("mvn")
if not shutil.which("java"): raise SystemExit("Java 17 이상을 설치하고 VS Code를 다시 실행하세요.")
if not mvn:
    archive=root/"tools/apache-maven.zip"
    url="https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip"
    print("Maven 다운로드:",url,flush=True)
    urllib.request.urlretrieve(url,archive)
    with zipfile.ZipFile(archive) as z: z.extractall(root/"tools")
    mvn=str(root/"tools/apache-maven-3.9.9/bin"/("mvn.cmd" if __import__('os').name=="nt" else "mvn"))
subprocess.run([mvn,"-B","-f",str(root/"tools/converter/pom.xml"),"package","-DskipTests"],check=True)
print("변환기 준비 완료")
