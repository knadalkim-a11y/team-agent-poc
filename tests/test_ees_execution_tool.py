"""Retired AI mutation contracts are replaced by an explicit read/propose surface.

Execution, intent consumption and approvals are exercised through Operations
and real authenticated Native routes in their integration suites.
"""
import inspect
import unittest
from test_ees_workflow_tool import tool_module


class ExecutionToolTests(unittest.TestCase):
    def test_ai_public_surface_has_no_mutation_or_intent_endpoint(self):
        names = {name for name, value in vars(tool_module.Tools).items()
                 if not name.startswith('_') and inspect.iscoroutinefunction(value)}
        self.assertEqual(names, {'ees_workflow_view', 'ees_workflow_propose', 'ees_workflow_display'})
        for name in ('ees_workflow_action', 'ees_execution_plan', 'ees_execution_action', 'request_dispatch',
                     'workspace_command', 'publish', 'confirm', 'intent'):
            self.assertFalse(hasattr(tool_module.Tools, name), name)

    def test_fixed_browser_bridge_rejects_unapproved_method(self):
        import asyncio
        from unittest.mock import AsyncMock
        event = AsyncMock()
        result = asyncio.run(tool_module._browser(event, 'chat', 'workspace_command', {'action': 'publish'}))
        self.assertFalse(result['ok']); event.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
