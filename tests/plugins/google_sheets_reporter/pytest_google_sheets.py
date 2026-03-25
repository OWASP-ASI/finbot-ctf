import re
import json
import gspread
from datetime import datetime
from typing import Optional, Dict, List
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import os
import pytest

# Load environment variables at module level
load_dotenv()

# Constants for worksheet names
LLM_CLIENT = 'LLM Client'
LLM_MOCK_CLIENT = 'LLM Mock Client'
LLM_OLLAMA_CLIENT = 'LLM Ollama Client'
LLM_OPENAI_CLIENT = 'LLM OpenAI Client'
LLM_CONTEXTUAL_CLIENT = 'LLM Contextual Client'
COMPLETE_USER_ISOLATION = 'Complete User Isolation'
ISOLATION_TESTING_FRAMEWORK = 'Isolation Testing Framework TCs'
SECURE_SESSION_MANAGEMENT = 'Secure Session Management'
BASE_AGENT_FRAMEWORK = 'Base Agent Framework'
SPECIALIZED_BUSINESS_AGENT = 'Specialized Business Agent'
EVENT_DRIVEN_CTF = 'Event Driven CTF'
MULTI_DB_SUPPORT = 'Multi-DB-Support'
REDIS_MESSAGE_STREAMS = 'Redis Message Streams'


class GoogleSheetsReporter:
    """Handles updating a specific Google Sheets worksheet with test results."""

    def __init__(self, worksheet_name: str):
        """Store config; defer Google API connection until first write."""
        self.worksheet_name = worksheet_name
        self.results: List[dict] = []

        # Validate required env vars eagerly (fast, no network)
        self._credentials_json = os.getenv('GOOGLE_CREDENTIALS')
        self._sheets_id = os.getenv('GOOGLE_SHEETS_ID')
        if not self._sheets_id:
            raise ValueError("GOOGLE_SHEETS_ID not set in environment")
        self._credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'google-credentials.json')

        # Lazily initialized on first write
        self.worksheet = None

    def _ensure_connected(self):
        """Connect to Google Sheets on demand (called before any sheet operation)."""
        if self.worksheet is not None:
            return

        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        if self._credentials_json:
            credentials = Credentials.from_service_account_info(
                json.loads(self._credentials_json), scopes=scopes
            )
        else:
            credentials = Credentials.from_service_account_file(
                self._credentials_file, scopes=scopes
            )
        client = gspread.authorize(credentials)
        # Prevent indefinite hangs on network calls (connect_timeout, read_timeout)
        client.http_client.timeout = (10, 30)
        sheet = client.open_by_key(self._sheets_id)

        # Get existing worksheet — never create a new tab
        self.worksheet = sheet.worksheet(self.worksheet_name)

    def record_result(self, test_code: str, test_name: str, status: str, duration: float, message: str = ""):
        """Record a single test result."""
        row = {
            'code': test_code,
            'name': test_name,
            'status': status,
            'duration': f"{duration:.2f}",
            'timestamp': datetime.now().isoformat(),
            'message': message
        }
        self.results.append(row)

    def _find_row(self, col_a: list, test_code: str, test_name: str) -> Optional[int]:
        """Return 1-indexed row number in col_a matching test_code or test_name, or None.

        test_code uses exact match to avoid 'BA-1' matching 'BA-10'.
        test_name falls back to substring match since it has no fixed format.
        """
        # Exact match on test_code (skip header row at index 0)
        if test_code:
            code = test_code.strip().lower()
            for i, cell_value in enumerate(col_a[1:], start=2):
                if cell_value and str(cell_value).strip().lower() == code:
                    return i

        # Substring match on test_name as fallback (skip header row)
        if test_name:
            name = test_name.strip().lower()
            for i, cell_value in enumerate(col_a[1:], start=2):
                if cell_value and name in str(cell_value).strip().lower():
                    return i

        return None

    def save_results(self):
        """Save all accumulated results to the worksheet in a single batch.

        Reads column A once, matches every result to its US ID row, then writes
        all K/L/M cells in one update_cells call — avoids rate-limiting from
        making individual API calls per test result.
        """
        if not self.results:
            return

        self._ensure_connected()
        col_a = self.worksheet.col_values(1)
        cells_to_update = []
        timestamp = datetime.now().isoformat()

        for result in self.results:
            test_code = result['code']
            test_name = result['name']
            status = result['status']
            message = result['message']

            row = self._find_row(col_a, test_code, test_name)
            if row is None:
                print(
                    f"  [sheets] no match for '{test_code}' in '{self.worksheet_name}' "
                    f"col A — verify the US ID exists in the sheet"
                )
                continue

            cells_to_update.extend([
                gspread.Cell(row, 11, status),
                gspread.Cell(row, 12, message),
                gspread.Cell(row, 13, timestamp),
            ])

        if cells_to_update:
            self.worksheet.update_cells(cells_to_update)

        self.results = []

    def save_summary_results(self, results_dicts: list):
        """Save summary with one row per test suite."""
        if not results_dicts:
            return

        results_by_worksheet = {}
        for result in results_dicts:
            ws = result.get('worksheet', 'Unknown')
            if ws not in results_by_worksheet:
                results_by_worksheet[ws] = []
            results_by_worksheet[ws].append(result)

        for worksheet_name, worksheet_results in results_by_worksheet.items():
            self._save_summary_row_for_worksheet(worksheet_name, worksheet_results)

    def _save_summary_row_for_worksheet(self, worksheet_name: str, results: list):
        """Create summary row for a specific worksheet."""
        self._ensure_connected()
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r['status'] == 'PASSED')
        failed_tests = sum(1 for r in results if r['status'] == 'FAILED')
        pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        total_duration = sum(float(r['duration']) for r in results)

        test_names = "\n".join([
            f"{r['code']}: {r['name']} ({r['duration']:.2f}s)"
            for r in results
        ])

        statuses_str = "\n".join([r['status'] for r in results])

        summary_row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            worksheet_name,
            total_tests,
            passed_tests,
            failed_tests,
            f"{pass_rate:.1f}%",
            f"{total_duration:.2f}",
            test_names,
            statuses_str
        ]
        self.worksheet.insert_row(summary_row, index=2)


def extract_iso_code(docstring: Optional[str]) -> Optional[str]:
    """Extract test code from docstring (ISO-*, SSM-*, CUI-*, etc.)."""
    if not docstring:
        return None
    match = re.search(r'([A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d+)', docstring)
    return match.group(1) if match else None


def detect_test_category(item) -> str:
    """Detect which Google Sheets worksheet a test belongs to based on file path."""
    full_path = str(item.fspath).lower()

    # Strip everything before the first 'tests/' component so that keywords
    # in the project root directory (e.g. 'finbot-ctf' matching 'ctf') are
    # not falsely matched.
    tests_idx = full_path.find('/tests/')
    fspath = full_path[tests_idx:] if tests_idx >= 0 else full_path

    # LLM-specific detection — checked first to avoid matching generic keywords
    if '/llm/' in fspath or '\\llm\\' in fspath:
        if 'test_llm_client' in fspath:
            return LLM_CLIENT
        if 'test_mock_client' in fspath:
            return LLM_MOCK_CLIENT
        if 'test_ollama_client' in fspath:
            return LLM_OLLAMA_CLIENT
        if 'test_openai_client' in fspath:
            return LLM_OPENAI_CLIENT
        if 'test_contextual_client' in fspath:
            return LLM_CONTEXTUAL_CLIENT
        # Unrecognized LLM test file — default to LLM_CLIENT rather than
        # silently routing to ISOLATION_TESTING_FRAMEWORK
        return LLM_CLIENT

    path_worksheet_map = {
        'complete_user_isolation': COMPLETE_USER_ISOLATION,
        'redis_message_streams': REDIS_MESSAGE_STREAMS,
        'specialized': SPECIALIZED_BUSINESS_AGENT,
        'agents': BASE_AGENT_FRAMEWORK,
        'isolation': ISOLATION_TESTING_FRAMEWORK,
        'vendor': ISOLATION_TESTING_FRAMEWORK,
        'auth': SECURE_SESSION_MANAGEMENT,
        'session': SECURE_SESSION_MANAGEMENT,
        'security': 'Security Penetration Testing',
        'test_event_driven_ctf_backend': EVENT_DRIVEN_CTF,
        'ctf': 'CTF Challenge Validation',
        'performance': 'Performance Testing',
        'browser': 'Cross_Browser',
        'e2e': 'End-To-End',
        'integration': 'End-To-End',
        'database': MULTI_DB_SUPPORT,
        'google_sheets': 'Google Sheets Integration',
        'summary': 'Summary',
        'mcp': 'MCP',
    }

    for keyword, worksheet in path_worksheet_map.items():
        if keyword in fspath:
            return worksheet

    return ISOLATION_TESTING_FRAMEWORK


class GoogleSheetsPlugin:
    """Pytest plugin for automatic Google Sheets test result reporting."""

    UPDATABLE_WORKSHEETS = {
        ISOLATION_TESTING_FRAMEWORK,
        REDIS_MESSAGE_STREAMS,
        SECURE_SESSION_MANAGEMENT,
        COMPLETE_USER_ISOLATION,
        BASE_AGENT_FRAMEWORK,
        SPECIALIZED_BUSINESS_AGENT,
        EVENT_DRIVEN_CTF,
        MULTI_DB_SUPPORT,
        LLM_CLIENT,
        LLM_MOCK_CLIENT,
        LLM_OLLAMA_CLIENT,
        LLM_OPENAI_CLIENT,
        LLM_CONTEXTUAL_CLIENT,
        'MCP',
    }

    def __init__(self, config):
        self.config = config
        self.reporters: Dict[str, GoogleSheetsReporter] = {}
        self.results_by_worksheet: Dict[str, List] = {}
        self.session_start_time = datetime.now()
        self.test_count = 0
        self.passed_count = 0
        self.failed_count = 0

        if config.getoption("--google-sheets"):
            worksheets = [
                ISOLATION_TESTING_FRAMEWORK,
                REDIS_MESSAGE_STREAMS,
                SECURE_SESSION_MANAGEMENT,
                BASE_AGENT_FRAMEWORK,
                SPECIALIZED_BUSINESS_AGENT,
                EVENT_DRIVEN_CTF,
                MULTI_DB_SUPPORT,
                'Security Penetration Testing',
                'CTF Challenge Validation',
                'Performance Testing',
                'Cross_Browser',
                'End-To-End',
                LLM_CLIENT,
                LLM_MOCK_CLIENT,
                LLM_OLLAMA_CLIENT,
                LLM_OPENAI_CLIENT,
                LLM_CONTEXTUAL_CLIENT,
                COMPLETE_USER_ISOLATION,
                'Summary',
                'MCP',
            ]

            for worksheet_name in worksheets:
                self.results_by_worksheet[worksheet_name] = []
                try:
                    self.reporters[worksheet_name] = GoogleSheetsReporter(worksheet_name)
                except Exception as e:
                    print(f"⚠️  Could not initialize worksheet '{worksheet_name}': {e}")

    def _get_test_status(self, report) -> str:
        """Determine test status from report."""
        if report.passed:
            return "PASSED"
        elif report.skipped:
            return "SKIPPED"
        return "FAILED"

    def _update_counters(self, status: str) -> None:
        """Update test counts based on status."""
        self.test_count += 1
        if status == "PASSED":
            self.passed_count += 1
        elif status == "FAILED":
            self.failed_count += 1

    def _record_test_result(self, item, report, worksheet_name: str) -> None:
        """Build and record a test result."""
        test_code = extract_iso_code(item.obj.__doc__)
        status = self._get_test_status(report)
        message = str(report.longrepr) if report.longrepr else ""

        self._update_counters(status)

        result = {
            'code': test_code or item.name,
            'name': item.name,
            'status': status,
            'duration': report.duration,
            'message': message,
            'worksheet': worksheet_name
        }

        if worksheet_name in self.results_by_worksheet:
            self.results_by_worksheet[worksheet_name].append(result)

        if 'Summary' in self.results_by_worksheet:
            self.results_by_worksheet['Summary'].append(result)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        """Hook to capture test results and update Google Sheets."""
        outcome = yield
        report = outcome.get_result()

        if not self.config.getoption("--google-sheets"):
            return

        # Skipped tests only have a "setup" phase — "call" is never reached.
        # Passing/failing tests are captured from "call".
        is_call_result = report.when == "call"
        is_skip_result = report.when == "setup" and report.skipped

        if is_call_result or is_skip_result:
            worksheet_name = detect_test_category(item)
            self._record_test_result(item, report, worksheet_name)

    def _flush_worksheet(self, worksheet_name: str, results: list) -> tuple:
        """Record and save results for one worksheet. Returns (passed_count, total_count)."""
        total_count = len(results)
        passed_count = sum(1 for r in results if r['status'] == 'PASSED')
        if worksheet_name not in self.reporters:
            print(f"⊗ Skipping '{worksheet_name}' — reporter not initialized (check credentials/tab permissions)")
            return passed_count, total_count
        try:
            for result in results:
                self.reporters[worksheet_name].record_result(
                    result['code'], result['name'], result['status'],
                    result['duration'], result['message']
                )
            self.reporters[worksheet_name].save_results()
            print(f"✓ Saved {total_count} results to '{worksheet_name}' ({passed_count}/{total_count} passed)")
        except Exception as e:
            print(f"✗ ERROR saving to '{worksheet_name}': {e}")
        return passed_count, total_count

    def _print_breakdown(self) -> None:
        """Print per-worksheet pass/fail counts."""
        print("\nWorksheet Breakdown:")
        print("=" * 80)
        for worksheet_name, results in self.results_by_worksheet.items():
            if results and worksheet_name != "Summary":
                passed = sum(1 for r in results if r['status'] == 'PASSED')
                print(f"✓ {worksheet_name}: {passed}/{len(results)} passed")

    def pytest_sessionfinish(self):
        """Hook called after all tests complete."""
        if not self.config.getoption("--google-sheets"):
            return

        print("\n" + "=" * 80)
        print("Google Sheets Test Results Summary")
        print("=" * 80)

        total_tests = 0
        passed_tests = 0
        worksheet_count = 0

        for worksheet_name, results in self.results_by_worksheet.items():
            if results and worksheet_name != "Summary" and worksheet_name in self.UPDATABLE_WORKSHEETS:
                worksheet_count += 1
                passed_count, total_count = self._flush_worksheet(worksheet_name, results)
                passed_tests += passed_count
                total_tests += total_count

        if "Summary" in self.results_by_worksheet and self.reporters.get("Summary"):
            try:
                self.reporters["Summary"].save_summary_results(self.results_by_worksheet["Summary"])
                print(f"✓ Saved Summary ({len(self.results_by_worksheet['Summary'])} total tests)")
            except Exception as e:
                print(f"✗ ERROR saving to Summary: {e}")

        if total_tests > 0:
            pass_rate = (passed_tests / total_tests) * 100
            print(f"\nOverall: {passed_tests}/{total_tests} passed ({pass_rate:.1f}%)")

        self._print_breakdown()
        print(f"✓ Results saved to {worksheet_count} worksheet(s)")
        print("=" * 90)


# Module-level pytest hooks
def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--google-sheets",
        action="store_true",
        default=False,
        help="Enable automatic Google Sheets test result reporting"
    )


def pytest_configure(config):
    """Register the plugin."""
    config.addinivalue_line(
        "markers", "google_sheets: mark test to report to Google Sheets"
    )
    if config.getoption("--google-sheets"):
        plugin = GoogleSheetsPlugin(config)
        config.pluginmanager.register(plugin)
