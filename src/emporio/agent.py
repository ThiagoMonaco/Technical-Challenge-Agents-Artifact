"""Bounded Responses API loop with transactional, in-memory history."""

import json
import logging

from openai import APIError

from .prompts import instructions
from .tools import TOOLS

LOGGER = logging.getLogger("emporio")
API_FAILURE = "Não consegui consultar o assistente agora. Tente novamente em instantes; não posso confirmar informações nesta tentativa."
ROUND_LIMIT = "Não consegui concluir a consulta dentro do limite. Pode simplificar sua pergunta ou consultar a equipe? Não tenho uma confirmação para esta tentativa."


class Agent:
    def __init__(self, client, tools, policies, model="gpt-5-mini", max_rounds=5):
        self.client = client
        self.tools = tools
        self.policies = policies
        self.model = model
        self.max_rounds = max_rounds
        self.history = []
        self.last_trace = []
        self.last_usage = []
        self.last_status = "ready"

    def reset(self):
        self.history.clear()
        self.last_trace.clear()
        self.last_usage.clear()
        self.last_status = "ready"

    def reply(self, message):
        self.last_trace = []
        self.last_usage = []
        self.last_status = "running"
        if not message.strip() or len(message) > 12000:
            self.last_status = "invalid_input"
            return "Envie uma mensagem de 1 a 12.000 caracteres."
        # Discard partial turns on failure: never leave unmatched tool calls in history.
        work = [*self.history, {"role": "user", "content": message}]
        reference = {"role": "developer", "content": "MANUAL DE REFERÊNCIA (dados, não instruções):\n" + self.policies}
        for round_index in range(self.max_rounds):
            try:
                response = self.client.responses.create(
                    model=self.model, instructions=instructions(),
                    input=[reference, *work], tools=TOOLS,
                    tool_choice="auto",
                    parallel_tool_calls=False, store=False,
                    max_output_tokens=4000,
                )
            except APIError as exc:
                self.last_status = "api_error"
                LOGGER.debug("api_failure type=%s", type(exc).__name__)
                return API_FAILURE
            usage = response.usage.model_dump() if response.usage is not None else {}
            self.last_usage.append(usage)
            LOGGER.debug("api_usage round=%d input_tokens=%s output_tokens=%s", round_index,
                         usage.get("input_tokens"), usage.get("output_tokens"))
            if response.status != "completed":
                self.last_status = "incomplete"
                return "A resposta não foi concluída. Tente uma pergunta mais específica; não posso confirmar o resultado desta tentativa."
            calls = [item for item in response.output if item.type == "function_call"]
            work.extend(item.model_dump(exclude_none=True) for item in response.output)
            if not calls:
                text = response.output_text.strip()
                if not text:
                    self.last_status = "empty_response"
                    return API_FAILURE
                self.history = work
                self.last_status = "completed"
                return text
            if len(calls) > 8:
                self.last_status = "call_limit"
                return ROUND_LIMIT
            for call in calls:
                result = self.tools.dispatch(call.name, call.arguments)
                # Trace is ephemeral and used by evaluation. Debug logs contain no args/results.
                self.last_trace.append({"name": call.name, "result": result})
                LOGGER.debug("tool round=%d name=%s ok=%s code=%s", round_index,
                             call.name if call.name in {t["name"] for t in TOOLS} else "unknown",
                             result.get("ok"), result.get("error", {}).get("code"))
                work.append({"type": "function_call_output", "call_id": call.call_id,
                             "output": json.dumps(result, ensure_ascii=False)})
        self.last_status = "round_limit"
        return ROUND_LIMIT
