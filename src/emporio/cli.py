"""Terminal interface and repeatable setup/evaluation commands."""

import argparse
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from .agent import Agent
from .data import DB_PATH, POLICY_PATH, ROOT, DataError, build, connect
from .tools import StoreTools


def make_agent(customer_id=None):
    load_dotenv(ROOT / ".env")
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise DataError("Configure OPENAI_API_KEY no ambiente ou em .env (veja .env.example).")
    try:
        timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "45"))
        if not 1 <= timeout <= 300:
            raise ValueError
    except ValueError as exc:
        raise DataError("OPENAI_TIMEOUT_SECONDS deve estar entre 1 e 300.") from exc
    with connect(DB_PATH) as db:
        if customer_id is not None and not db.execute(
                "SELECT 1 FROM customers WHERE customer_id=?", (customer_id,)).fetchone():
            raise DataError("Cliente de demonstração inválido.")
    if not POLICY_PATH.is_file():
        raise DataError("Manual não preparado. Execute: emporio setup")
    if os.getenv("EMPORIO_DEBUG") == "1":
        logger = logging.getLogger("emporio")
        logger.setLevel(logging.DEBUG)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            logger.addHandler(handler)
        logger.propagate = False
    client = OpenAI(api_key=key, timeout=timeout, max_retries=1)
    return Agent(client, StoreTools(DB_PATH, customer_id), POLICY_PATH.read_text(encoding="utf-8"),
                 model=os.getenv("OPENAI_MODEL", "gpt-5-mini"))


def chat(agent):
    print("Empório da Música — assistente virtual (dados de demonstração).")
    print("Identidade simulada fixa na inicialização. /help para comandos. Ctrl-D para sair.")
    while True:
        try:
            message = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAté mais!")
            return
        if message == "/exit":
            return
        if message == "/reset":
            agent.reset()
            print("Histórico apagado; identidade da sessão mantida.")
        elif message == "/help":
            print("/reset apaga histórico; /exit sai; /help mostra ajuda. Pergunte sobre instrumentos, pedidos e políticas.")
        elif message:
            try:
                print("Assistente:", agent.reply(message))
            except KeyboardInterrupt:
                print("\nConsulta interrompida; tente novamente.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Agente do Empório da Música")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Valida CSVs, cria SQLite e extrai manual; não usa API")
    terminal = sub.add_parser("chat", help="Chat com OpenAI; usa API paga")
    terminal.add_argument("--customer-id", type=int)
    evaluate = sub.add_parser("evaluate", help="Executa cenários reais; usa API paga")
    evaluate.add_argument("--output", type=Path, default=ROOT / "evaluation" / "runs" / "latest")
    evaluate.add_argument("--case", action="append", dest="cases", help="Executa somente o ID indicado; pode repetir")
    evaluate.add_argument("--record-examples", action="store_true", help="Grava cinco transcrições reais em examples/ após execução completa")
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            print(json.dumps(build(), ensure_ascii=False, indent=2))
        elif args.command == "chat":
            chat(make_agent(args.customer_id))
        else:
            from .evaluation import run
            raise SystemExit(run(make_agent, args.output, args.cases, args.record_examples))
    except (DataError, OSError) as exc:
        parser.exit(2, f"Erro: {exc}\n")
