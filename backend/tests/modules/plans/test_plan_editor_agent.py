import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.plans.plan_editor.agent import PlanEditorAgent
from app.modules.plans.plan_editor.contract import PlanEditorOperation


def _plan(*, locked=False):
    item = SimpleNamespace(
        item_id="item-1",
        name="Museum",
        locked=locked,
        source_refs=["source-old"],
        candidate_entity_ids=["entity-old"],
        source_provider="kg",
        identity_confidence="high",
        source_import_node_id=3,
    )
    return SimpleNamespace(days=[SimpleNamespace(day=1, items=[item])])


def _result(affected_days=(1, 2)):
    report = SimpleNamespace(issues=[])
    return SimpleNamespace(
        plan=SimpleNamespace(),
        affected_days=list(affected_days),
        check_report=report,
    )


def _agent(service):
    checker = Mock()
    checker.check.return_value = SimpleNamespace(issues=[])
    service.checker = checker
    return PlanEditorAgent(Mock(), Mock(), service)


def test_each_supported_operation_calls_its_mutation_method():
    service = SimpleNamespace(
        add_item=AsyncMock(return_value=_result((1,))),
        update_item=AsyncMock(return_value=_result((1,))),
        remove_item=Mock(return_value=_result((1,))),
        move_item=Mock(return_value=_result((1, 2))),
    )
    agent = _agent(service)
    plan = _plan()

    asyncio.run(agent.execute(
        plan=plan, chat=SimpleNamespace(), turn=SimpleNamespace(),
        intent="add_place", operation={"type": "add_place", "day": 1, "name": "Cafe"},
    ))
    asyncio.run(agent.execute(
        plan=plan, chat=SimpleNamespace(), turn=SimpleNamespace(),
        intent="update_place", operation={"type": "update_place", "day": 1, "itemId": "item-1", "name": "Gallery"},
    ))
    asyncio.run(agent.execute(
        plan=plan, chat=SimpleNamespace(), turn=SimpleNamespace(),
        intent="remove_place", operation={"type": "remove_place", "day": 1, "itemId": "item-1"},
    ))
    asyncio.run(agent.execute(
        plan=plan, chat=SimpleNamespace(), turn=SimpleNamespace(),
        intent="move_place", operation={"type": "move_place", "day": 1, "toDay": 2, "itemId": "item-1"},
    ))

    assert service.add_item.await_count == 1
    assert service.update_item.await_count == 1
    service.remove_item.assert_called_once_with(plan, 1, "item-1")
    service.move_item.assert_called_once_with(plan, 1, "item-1", service.move_item.call_args.args[3])


def test_locked_item_does_not_write_without_confirmation():
    service = SimpleNamespace(update_item=AsyncMock(return_value=_result()))
    agent = _agent(service)

    with pytest.raises(Exception) as error:
        asyncio.run(agent.execute(
            plan=_plan(locked=True), chat=SimpleNamespace(), turn=SimpleNamespace(),
            intent="update_place",
            operation={"type": "update_place", "day": 1, "itemId": "item-1", "name": "Gallery"},
        ))

    assert getattr(error.value, "code", None) == "LOCKED_ITEM"
    service.update_item.assert_not_called()


def test_unsupported_operation_does_not_call_service():
    service = SimpleNamespace()
    agent = _agent(service)

    with pytest.raises(Exception) as error:
        asyncio.run(agent.execute(
            plan=_plan(), chat=SimpleNamespace(), turn=SimpleNamespace(),
            intent="reorder_items", operation={"type": "reorder_items"},
        ))

    assert getattr(error.value, "code", None) == "UNSUPPORTED_OPERATION"


def test_new_checker_error_is_rejected_before_caller_can_persist():
    result = _result((1,))
    result.check_report = SimpleNamespace(
        issues=[SimpleNamespace(code="OVERLAP", severity="error")]
    )
    service = SimpleNamespace(add_item=AsyncMock(return_value=result))
    checker = Mock()
    checker.check.return_value = SimpleNamespace(issues=[])
    service.checker = checker
    agent = PlanEditorAgent(Mock(), Mock(), service)

    with pytest.raises(Exception) as error:
        asyncio.run(agent.execute(
            plan=_plan(), chat=SimpleNamespace(), turn=SimpleNamespace(),
            intent="add_place", operation={"type": "add_place", "day": 1, "name": "Cafe"},
        ))

    assert getattr(error.value, "code", None) == "MUTATION_VALIDATION_FAILED"


def test_lock_and_unlock_use_update_item_with_expected_flag():
    service = SimpleNamespace(update_item=AsyncMock(return_value=_result((1,))))
    agent = _agent(service)
    operation = {"type": "lock_item", "day": 1, "itemId": "item-1"}

    asyncio.run(agent.execute(plan=_plan(), chat=SimpleNamespace(), turn=SimpleNamespace(), intent="lock_item", operation=operation))
    asyncio.run(agent.execute(
        plan=_plan(locked=True), chat=SimpleNamespace(), turn=SimpleNamespace(),
        intent="unlock_item", operation={"type": "unlock_item", "day": 1, "itemId": "item-1"},
    ))

    assert [call.args[3].locked for call in service.update_item.await_args_list] == [True, False]
