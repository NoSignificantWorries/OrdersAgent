import asyncio
import json
from typing import Optional

from temporalio.client import Client


async def send_answer(workflow_id: str, answers_file: Optional[str] = None):
    client = await Client.connect("localhost:7233", namespace="default")

    handle = client.get_workflow_handle(workflow_id)

    if answers_file:
        with open(answers_file, "r") as f:
            answers = json.load(f)
    else:
        answers = {"14": ("test14", True), "4HPBronze20": ("Bronze20", False)}

    await handle.signal("provide_material_answers", answers)
    print(f"✅ Signal sent to workflow {workflow_id}")
    print(f"Answers: {json.dumps(answers, indent=2, ensure_ascii=False)}")


async def list_waiting_workflows():
    client = await Client.connect("localhost:7233", namespace="default")

    print("🔍 Searching for waiting workflows...")
    async for wf in client.list_workflows("WorkflowType='ExcelProcessingWorkflow'"):
        handle = client.get_workflow_handle(wf.id)
        try:
            status = await handle.query("get_status")
            if status == "waiting_for_user":
                print(f"\n📋 Workflow: {wf.id}")
                questions = await handle.query("get_questions")
                if questions:
                    print(
                        f"Questions: {json.dumps(questions, indent=2, ensure_ascii=False)}"
                    )
        except:
            pass


async def interactive_debug():
    client = await Client.connect("localhost:7233", namespace="default")

    waiting = []
    async for wf in client.list_workflows("WorkflowType='ExcelProcessingWorkflow'"):
        handle = client.get_workflow_handle(wf.id)
        try:
            status = await handle.query("get_status")
            if status == "waiting_for_user":
                waiting.append((wf.id, handle))
        except:
            pass

    if not waiting:
        print("❌ No workflows waiting for user input")
        return

    print(f"Found {len(waiting)} waiting workflow(s):\n")

    for i, (wf_id, handle) in enumerate(waiting):
        print(f"{i + 1}. {wf_id}")
        questions = await handle.query("get_questions")
        if questions:
            for part, black_list in questions.items():
                print(f"  Part: {part} (black_list: {black_list})")

    choice = int(input("\nSelect workflow number: ")) - 1
    wf_id, handle = waiting[choice]

    questions = await handle.query("get_questions")

    answers = {}
    print("\n📝 Enter answers for each question:")
    for part, black_list in questions.items():
        answer = input(f"For part '{part}': ")
        bl = input(f"Black list for part '{part}': ") == "1"
        answers[part] = (answer, bl)

    await handle.signal("provide_material_answers", answers)
    print(f"\n✅ Answers sent to {wf_id}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "list":
        asyncio.run(list_waiting_workflows())
    elif len(sys.argv) > 2 and sys.argv[1] == "send":
        wf_id = sys.argv[2]
        answers_file = sys.argv[3] if len(sys.argv) > 3 else None
        asyncio.run(send_answer(wf_id, answers_file))
    else:
        asyncio.run(interactive_debug())
