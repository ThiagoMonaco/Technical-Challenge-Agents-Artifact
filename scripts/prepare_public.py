"""Replay real local milestones into a publication copy with synthetic customer contacts.

Never push the private source repository. This command does not access the network,
alter source files, or rewrite local history. It requires a fresh output directory.
"""

import argparse
import csv
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


def git(root, *args, **kwargs):
    return subprocess.check_output(["git", "-C", str(root), *args], **kwargs)


def anonymize(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    for row in rows:
        ident = int(row["customer_id"])
        row.update(name=f"Cliente de demonstração {ident:03d}",
                   phone=f"(00) 00000-{ident:04d}",
                   email=f"cliente{ident:03d}@example.invalid", city="Cidade de demonstração")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


NOTICE = """# Dados da cópia pública

Esta cópia pública substitui nomes, telefones, e-mails e cidades dos clientes por
valores sintéticos em **todos os commits**, preservando IDs e relacionamentos para
que os mesmos testes e consultas funcionem. Endereços `example.invalid` e telefones
com DDD 00 são deliberadamente fictícios. Não permitem contatar pessoas reais.

Os marcos de implementação foram reproduzidos a partir dos commits reais locais;
os hashes mudam devido à anonimização. Os originais permanecem apenas no checkout
local de origem, que não deve ser enviado para este remoto. O script
`scripts/prepare_public.py` reproduz o processo sem alterar os arquivos originais.

O manual descreve uma loja fictícia; seus contatos institucionais fazem parte do
material do desafio. As relações comerciais e IDs permanecem os do snapshot.
"""


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Use um diretório de saída novo; nenhuma cópia existente será sobrescrita.")
    commits = git(source, "rev-list", "--reverse", "HEAD").decode().splitlines()
    output.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(output)], check=True, stdout=subprocess.DEVNULL)
    for commit in commits:
        names = git(source, "ls-tree", "-r", "--name-only", commit).decode().splitlines()
        if any(Path(name).name.startswith(".env") and Path(name).name != ".env.example" for name in names):
            raise ValueError("Histórico contém arquivo de ambiente privado; publicação interrompida.")
        for item in output.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()
        archive = git(source, "archive", commit)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(output, filter="data")
        for path in (output / "data").glob("* - customers.csv"):
            anonymize(path)
        (output / "PUBLICATION.md").write_text(NOTICE, encoding="utf-8")
        metadata = git(source, "show", "-s", "--format=%an%x00%ae%x00%aI%x00%cI%x00%B", commit).decode()
        author, email, author_date, commit_date, message = metadata.split("\0", 4)
        env = {**os.environ, "GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": email,
               "GIT_AUTHOR_DATE": author_date, "GIT_COMMITTER_DATE": commit_date}
        git(output, "add", "--all")
        subprocess.run(["git", "-C", str(output), "commit", "--allow-empty", "-F", "-"],
                       input=message.encode(), env=env, check=True, stdout=subprocess.DEVNULL)
    return len(commits)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    count = prepare(root, args.output)
    print(f"Cópia pública preparada em {args.output}; {count} marcos preservados; sem acesso à rede.")
