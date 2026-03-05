"""
Parallel tool executor for concurrent tool execution. Runs multiple tool calls simultaneously using thread pool.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Callable


class ParallelToolExecutor:

    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers

    def execute_batch(self, tool_calls: list, execute_fn: Callable) -> List[dict]:
        if not tool_calls:
            return []

        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_call = {}

            for tc in tool_calls:
                tool_name = tc["function"]["name"]

                try:
                    arguments = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    arguments = {}

                future = executor.submit(execute_fn, tool_name, arguments)
                future_to_call[future] = tc

            for future in as_completed(future_to_call):
                tc = future_to_call[future]

                try:
                    result = future.result(timeout=30)
                except Exception as e:
                    result = json.dumps({"success": False, "error": str(e)})

                results.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["function"]["name"],
                    "content": result
                })

        return results


if __name__ == "__main__":
    import time

    def example_tool_function(tool_name: str, arguments: dict) -> str:
        print(f"Executing {tool_name} with {arguments}")
        time.sleep(1)
        return json.dumps({
            "success": True,
            "tool": tool_name,
            "result": f"Completed {tool_name}"
        })

    tool_calls = [
        {
            "id": "call_1",
            "function": {
                "name": "get_weather",
                "arguments": '{"location": "Berlin"}'
            }
        },
        {
            "id": "call_2",
            "function": {
                "name": "get_parking",
                "arguments": '{"location": "Campus"}'
            }
        },
        {
            "id": "call_3",
            "function": {
                "name": "get_traffic",
                "arguments": '{"location": "Downtown"}'
            }
        }
    ]

    print("Testing ParallelToolExecutor...")
    print(f"Running {len(tool_calls)} tools in parallel\n")

    executor = ParallelToolExecutor(max_workers=3)

    start_time = time.time()
    results = executor.execute_batch(tool_calls, example_tool_function)
    elapsed = time.time() - start_time

    print(f"\nCompleted in {elapsed:.2f}s (would be ~{len(tool_calls)}s if sequential)")
    print(f"\nResults:")
    for result in results:
        print(f"  {result['name']}: {result['content'][:50]}...")
