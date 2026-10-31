"""Live transcripts plus mechanical checks; semantic review remains explicit."""

from datetime import datetime, timezone
import json
from pathlib import Path

from .data import ROOT, DataError


def run(factory, output, selected=None, record_examples=False):
    cases = json.loads((ROOT / "evaluation" / "cases.json").read_text(encoding="utf-8"))
    if selected:
        unknown = set(selected) - {case["id"] for case in cases}
        if unknown:
            raise DataError("Cenário desconhecido: " + ", ".join(sorted(unknown)))
        cases = [case for case in cases if case["id"] in selected]
    if record_examples and selected:
        raise DataError("Para registrar os cinco exemplos, execute todos os cenários sem --case.")
    # Validate credentials/setup before creating any misleading empty results.
    first_agent = factory(cases[0]["customer_id"])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "results.json").exists():
        raise DataError("Pasta já contém resultados. Use --output com um novo diretório para preservar a execução anterior.")
    stamp = datetime.now(timezone.utc).isoformat()
    results = []
    transcripts = {}
    for index, case in enumerate(cases):
        agent = first_agent if index == 0 else factory(case["customer_id"])
        turns = []
        trace = []
        content = [f"# {case['id']}", "", f"Execução real: {stamp}", f"Modelo: {agent.model}",
                   f"Cliente de demonstração: {case['customer_id']}", "",
                   "Revisão semântica: PENDENTE. Transcrição gerada pela API, não roteiro fabricado.", ""]
        for message in case["messages"]:
            answer = agent.reply(message)
            turns.append({"user": message, "assistant": answer, "status": agent.last_status,
                          "trace": agent.last_trace, "usage": agent.last_usage})
            trace.extend(agent.last_trace)
            content.extend([f"**Cliente:** {message}", "", f"**Assistente:** {answer}", "",
                            "Ferramentas: " + (", ".join(t["name"] for t in agent.last_trace) or "nenhuma"), ""])
        names = {item["name"] for item in trace}
        checks = {
            "completed": all(turn["status"] == "completed" for turn in turns),
            "required_tools": set(case["required_tools"]) <= names,
            "order_access": not case.get("all_order_results_denied") or all(
                not t["result"]["ok"] for t in trace if t["name"] == "get_order_status"),
        }
        result = {"id": case["id"], "model": agent.model, "timestamp": stamp,
                  "checks": checks, "automatic_pass": all(checks.values()),
                  "semantic_review": "pending", "expectation": case["expectation"], "turns": turns}
        results.append(result)
        transcript = "\n".join(content)
        transcripts[case["id"]] = transcript
        (output / f"{case['id']}.md").write_text(transcript, encoding="utf-8")
        # Save progressively so an interrupted paid evaluation retains completed work.
        (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{case['id']}: automático={'PASS' if result['automatic_pass'] else 'FAIL'}; revisão semântica pendente", flush=True)
    review = ["# Revisão de conversas reais", "", "Checks automáticos não comprovam correção semântica.",
              "Revise respostas contra ferramentas e seções do manual; registre PASS/FAIL e evidência.", ""]
    for result in results:
        review.extend([f"## {result['id']}", "", f"Esperado: {result['expectation']}", "",
                       "Resultado semântico: PENDENTE", "Evidência / correção: preencher após revisão", ""])
    (output / "review.md").write_text("\n".join(review), encoding="utf-8")
    if record_examples:
        # Only export complete API runs, never errors or mock output as examples.
        examples = [case for case in cases if case.get("example")]
        if all(result["automatic_pass"] for result in results):
            directory = ROOT / "examples"
            directory.mkdir(exist_ok=True)
            for case in examples:
                (directory / f"{case['id']}.md").write_text(transcripts[case["id"]], encoding="utf-8")
            print("Cinco transcrições reais salvas em examples/. Revise antes de entregar.")
        else:
            print("Exemplos não exportados: há falhas automáticas a corrigir.")
    print(f"Resultados: {output}; revisão semântica obrigatória em review.md")
    return 0 if all(r["automatic_pass"] for r in results) else 1
