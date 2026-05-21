"""
NLPController — Source-grounded extraction mixin

Contains extract_equation_from_sources() and
extract_animation_params_from_sources(): both take already-retrieved
chunks and pull out the specific shape the equation / animation
module needs. This grounds the extracted params in real retrieved
content rather than trusting the intent classifier.
"""

import json


class _NLPExtractionMixin:

    def extract_equation_from_sources(
        self, filtered_results: list, question: str
    ) -> str:
        """
        Extract the actual equation/formula text from retrieved chunks.
        Prioritizes equation/table chunk_types, then math-heavy text,
        then LLM-based extraction as a last resort.
        """
        equation_chunks = [
            r for r in filtered_results
            if r["payload"].get("chunk_type") in ("equation", "table")
        ]
        if equation_chunks:
            return equation_chunks[0]["payload"].get("text", "")

        math_chunks = [
            r for r in filtered_results
            if self._has_math_content(r["payload"].get("text", ""))
        ]
        if math_chunks:
            return math_chunks[0]["payload"].get("text", "")

        all_source_text = "\n\n".join(
            r["payload"].get("text", "") for r in filtered_results[:3]
        )
        extraction_prompt = (
            "From the following study material text, extract the mathematical "
            "equation, formula, or expression that the student is asking about.\n\n"
            f"Student question: {question}\n\n"
            f"Study material:\n{all_source_text}\n\n"
            "Return ONLY the equation/formula/expression. Nothing else. "
            'If no equation is found, return "NONE".'
        )
        try:
            extracted = self.generation_client.generate_text(
                prompt=extraction_prompt,
                chat_history=[],
                max_output_tokens=200,
                temperature=0.0,
            )
            if extracted and extracted.strip().upper() != "NONE":
                return extracted.strip()
        except Exception as e:
            self.logger.warning(f"Equation extraction failed: {e}")

        return question

    def extract_animation_params_from_sources(
        self,
        filtered_results: list,
        question: str,
        classifier_params: dict,
    ) -> dict:
        """
        Build animation spec from real retrieved content + classifier hints.
        Operation vocabulary is aligned with the Animation-Module branch
        (operationDispatcher.js): insertAtHead/insertAtTail/insertAtIndex,
        deleteAtHead/deleteAtTail/deleteByValue/deleteAtIndex, searchByValue,
        traverse, reverse.
        """
        data_structure = classifier_params.get("data_structure", "linked_list")
        operation = classifier_params.get("operation")
        initial_values = classifier_params.get("initial_values")

        all_source_text = "\n\n".join(
            r["payload"].get("text", "") for r in filtered_results[:3]
        )
        extraction_prompt = (
            "From the following study material, extract animation parameters "
            "for the student's request.\n\n"
            f"Student question: {question}\n\n"
            f"Study material:\n{all_source_text}\n\n"
            "Return ONLY a JSON object with these fields:\n"
            '- "data_structure": one of "linked_list", "binary_tree", '
            '"stack", "queue", "graph", "array"\n'
            '- "operation": one of "insertAtHead", "insertAtTail", '
            '"insertAtIndex", "deleteAtHead", "deleteAtTail", '
            '"deleteByValue", "deleteAtIndex", "searchByValue", '
            '"traverse", "reverse"\n'
            '- "initial_values": array of initial values, or null\n'
            '- "operation_params": object with {"value": <x>, "index": <i>} '
            "as appropriate\n\n"
            "JSON only, no explanation:"
        )
        try:
            raw = self.generation_client.generate_text(
                prompt=extraction_prompt,
                chat_history=[],
                max_output_tokens=300,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            if raw:
                params = json.loads(raw)
                data_structure = params.get("data_structure", data_structure)
                operation = params.get("operation", operation)
                if params.get("initial_values"):
                    initial_values = params["initial_values"]
                operation_params = params.get("operation_params", {})
                return {
                    "data_structure": data_structure,
                    "operation": operation,
                    "initial_values": initial_values,
                    "params": operation_params,
                    "source_grounded": True,
                }
        except Exception as e:
            self.logger.warning(f"Animation param extraction failed: {e}")

        return {
            "data_structure": data_structure,
            "operation": operation,
            "initial_values": initial_values,
            "params": classifier_params.get("operation_params", {}),
            "source_grounded": False,
        }
