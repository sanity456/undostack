import json
from pathlib import Path
import pytest


@pytest.fixture
def setup(direct_vm, direct_deploy, direct_alice, direct_bob):
    direct_vm.sender = direct_alice
    c = direct_deploy(str(Path(__file__).parents[1] / 'contracts/undo_stack.py'), sdk_version='v0.2.16')
    f = c.create_flow('event', 'Small community event equipment reservations.')
    c.add_step(f, 'Reserve table T1.', 'Release table T1 reservation.', direct_bob, [])
    c.add_step(f, 'Reserve chairs C1.', 'Release chairs C1 reservation.', direct_bob, [0])
    c.activate(f)
    return c, f, json.loads(c.get_flow(f))['plan_hash']


def mock(vm, answer):
    vm.clear_mocks()
    vm.mock_llm('UndoStack evidence', json.dumps({'verdict': answer}))


def test_reverse_dependency_rollback(setup, direct_vm, direct_alice, direct_bob):
    c, f, binding = setup
    direct_vm.sender = direct_bob
    mock(direct_vm, 'DONE')
    for i in range(2):
        c.start_step(f, i, binding)
        c.report_step(f, i, 'Reservation completed in full.')
    direct_vm.sender = direct_alice
    c.cancel(f, 'Event cancelled.')
    assert c.ready_undos(f) == [1]
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert('dependent steps first'):
        c.report_undo(f, 0, 'Released.')
    c.report_undo(f, 1, 'Chairs reservation fully released.')
    assert c.ready_undos(f) == [0]
    c.report_undo(f, 0, 'Table reservation fully released.')
    assert json.loads(c.get_flow(f))['state'] == 'ROLLED_BACK'
    assert c.ready_undos(f) == []


def test_cancel_waits_for_running_step(setup, direct_vm, direct_alice, direct_bob):
    c, f, binding = setup
    direct_vm.sender = direct_bob
    c.start_step(f, 0, binding)
    direct_vm.sender = direct_alice
    c.cancel(f, 'Cancelled while in flight.')
    assert json.loads(c.get_flow(f))['state'] == 'CANCELLING'
    assert c.ready_undos(f) == []
    direct_vm.sender = direct_bob
    mock(direct_vm, 'UNCERTAIN')
    c.report_step(f, 0, 'Partial reservation, awaiting response.')
    assert json.loads(c.get_flow(f))['state'] == 'CANCELLING'
    mock(direct_vm, 'NOT_DONE')
    c.report_step(f, 0, 'Supplier confirms no reservation was made and no effects occurred.')
    assert json.loads(c.get_flow(f))['state'] == 'ROLLED_BACK'


@pytest.mark.parametrize('answer', ['NOT_DONE','UNCERTAIN'])
def test_failed_undo_never_closes(setup, direct_vm, direct_alice, direct_bob, answer):
    c, f, binding = setup
    direct_vm.sender = direct_bob
    c.start_step(f, 0, binding)
    mock(direct_vm, 'DONE')
    c.report_step(f, 0, 'Reserved table.')
    direct_vm.sender = direct_alice
    c.cancel(f, 'Cancelled.')
    direct_vm.sender = direct_bob
    mock(direct_vm, answer)
    c.report_undo(f, 0, 'Release not confirmed.')
    assert c.ready_undos(f) == [0]
    assert json.loads(c.get_flow(f))['state'] == 'UNWINDING'


def test_independent_validator(setup, direct_vm, direct_bob):
    c, f, binding = setup
    direct_vm.sender = direct_bob
    c.start_step(f, 0, binding)
    mock(direct_vm, 'DONE')
    c.report_step(f, 0, 'Reservation completed.')
    assert direct_vm.run_validator(leader_result='DONE')
    assert not direct_vm.run_validator(leader_result='NOT_DONE')
    assert not direct_vm.run_validator(leader_result='garbage')
    assert not direct_vm.run_validator(leader_result={'verdict':'DONE'})


def test_access_binding_and_dependencies(setup, direct_vm, direct_bob, direct_charlie):
    c, f, binding = setup
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert('step actor only'):
        c.start_step(f, 0, binding)
    with direct_vm.expect_revert('active owner only'):
        c.cancel(f, 'Malicious cancel.')
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert('dependency incomplete'):
        c.start_step(f, 1, binding)
    with direct_vm.expect_revert('stale plan'):
        c.start_step(f, 0, 'wrong')
    with direct_vm.expect_revert('running step required'):
        c.report_step(f, 0, 'Claimed without start.')


def test_terminal_flow_cannot_restart(setup, direct_vm, direct_alice, direct_bob):
    c, f, binding = setup
    c.cancel(f, 'Cancelled before any action.')
    assert json.loads(c.get_flow(f))['state'] == 'ROLLED_BACK'
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert('step unavailable'):
        c.start_step(f, 0, binding)


def test_normal_completion(setup, direct_vm, direct_alice, direct_bob):
    c, f, binding = setup
    direct_vm.sender = direct_bob
    mock(direct_vm, 'DONE')
    for i in range(2):
        c.start_step(f, i, binding)
        c.report_step(f, i, 'Completed all required effects.')
    direct_vm.sender = direct_alice
    c.finish(f)
    assert json.loads(c.get_flow(f))['state'] == 'COMPLETED'
    with direct_vm.expect_revert('active owner only'):
        c.cancel(f, 'Late cancellation.')


def test_invalid_dag_and_frozen_plan(setup, direct_vm, direct_bob):
    c, f, binding = setup
    with direct_vm.expect_revert('owner draft only'):
        c.add_step(f, 'X', 'Undo X', direct_bob, [])
    draft = c.create_flow('other', 'Another event.')
    with direct_vm.expect_revert('dependencies'):
        c.add_step(draft, 'X', 'Undo X', direct_bob, [0])
    c.add_step(draft, 'X', 'Undo X', direct_bob, [])
    with direct_vm.expect_revert('dependencies'):
        c.add_step(draft, 'Y', 'Undo Y', direct_bob, [0,0])


@pytest.mark.parametrize('answer', ['INVALID', True, None])
def test_malformed_result_no_mutation(setup, direct_vm, direct_bob, answer):
    c, f, binding = setup
    direct_vm.sender = direct_bob
    c.start_step(f, 0, binding)
    before = c.get_flow(f)
    mock(direct_vm, answer)
    with direct_vm.expect_revert():
        c.report_step(f, 0, 'Some report.')
    assert c.get_flow(f) == before
