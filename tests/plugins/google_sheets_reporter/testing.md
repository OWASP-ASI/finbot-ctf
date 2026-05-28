# 🧪 Testing Instructions

Follow these steps to run and record your test results for the Isolation Testing Framework.

## 1. Access the Test Cases

Open the test case spreadsheet:
https://docs.google.com/spreadsheets/d/1mdelmXYfarn7_xPNvNlSc9N5WH5S9kHQ2cEdPJmXeyA/edit?usp=sharing

Go to the "Isolation Testing Framework TCs" tab and add your name under the "Claimed By" column for the test case you are working on.

## 2. Run the Test Case

You may execute the test in one of three ways:

### Option A — Deployed Instance
Use the hosted instance here:
https://owasp-finbot-ctf.org/

### Option B — Local Environment
Run it locally. See setup instructions in this recording:
https://owasp.slack.com/archives/C09A2MFUXJ9/p1763385678934329

### Option C — Automated Testing with Google Sheets Integration (Recommended)

The test framework includes automated Google Sheets integration that automatically updates test results after each test run.

**Important:** Google Sheets updates only occur when using the `--google-sheets` flag with pytest. Running the application locally (Option B) or manual browser testing (Options A & B) will NOT update the spreadsheet automatically.

#### Prerequisites

1. **Python Environment**: Ensure you have Python 3.13+ installed
2. **Dependencies**: Install required packages:
   ```bash
   pip install pytest gspread google-auth
   ```

3. **Google Service Account** (if not already configured):
   - The spreadsheet is pre-configured with service account access
   - Contact the test lead if you need access

4. **Environment Variables**: Add to your `~/.zshrc` or `~/.bashrc`:
   ```bash
   export GOOGLE_SHEETS_ID="1mdelmXYfarn7_xPNvNlSc9N5WH5S9kHQ2cEdPJmXeyA"
   ```
   Then reload: `source ~/.zshrc`

#### Running Automated Tests

```bash
# Run all isolation tests WITH automatic Google Sheets reporting
pytest tests/unit/vendor/test_vendor_isolation.py --google-sheets -v

# Run a specific test case WITH Google Sheets updates
pytest tests/unit/vendor/test_vendor_isolation.py::test_basic_data_read_write_isolation --google-sheets -v

# Run WITHOUT Google Sheets updates (standard pytest - no spreadsheet changes)
pytest tests/unit/vendor/test_vendor_isolation.py -v
```

**Note:** The `--google-sheets` flag is required to update the spreadsheet. Without it, tests run normally but results are NOT recorded to Google Sheets.

#### What Gets Updated Automatically

When you run tests with the `--google-sheets` flag:
- ✅ **automation_status** column: Automatically set to `PASS` or `FAIL`
- ✅ **automation_notes** column: Error messages for failed tests (first 100 characters)
- ✅ **last_run** column: Timestamp of test execution
- ✅ **Summary** worksheet: Aggregated results with latest runs at the top

#### Console Output Example

```
✓ Initialized Google Sheets reporter for 'Isolation Testing Framework TCs'
================================================================================
Google Sheets Test Results Summary
================================================================================
Overall: 6/6 passed (100.0%)

Worksheet Breakdown:
  ✓ Isolation Testing Framework TCs: 6/6 (100.0%)
================================================================================
✓ Results saved to 1 worksheet(s) + Summary
```

## 3. Record the Results

### Manual Testing (Options A or B)

**If the test passes:**
- Set the **Status** column to `passed`
- Leave the **Actual Results** column empty

**If the test fails:**
- Set the **Status** column to `failed`
- Add the observed behavior to the **Actual Results** column
- Create a GitHub Issue (type: bug) here: https://github.com/GenAI-Security-Project/finbot-ctf/issues/new

### Automated Testing (Option C)

Results are automatically recorded! However, you should still:

**If the test fails:**
- Review the **automation_notes** column for error details
- Create a GitHub Issue (type: bug) here: https://github.com/GenAI-Security-Project/finbot-ctf/issues/new
- Add additional context in the **Actual Results** column if needed

## 4. Understanding Test Results

### Test Case Identifiers

Each test case has a unique ISO code format: `ISO-XXX-###`

Examples:
- `ISO-DAT-001`: Basic Data Read/Write Isolation
- `ISO-DAT-002`: Data Manipulation Isolation
- `ISO-DAT-003`: List/Aggregate Data Integrity
- `ISO-SES-001`: Forced Logout / Session Invalidation
- `ISO-SES-002`: Concurrent Session Overlap
- `ISO-NAM-001`: Namespace Integrity Checks

### Worksheet Columns

| Column | Description | Updated By |
|--------|-------------|------------|
| US ID | Test case identifier (e.g., ISO-DAT-001) | Manual |
| Test Case Name | Name of the test | Manual |
| ... | Other test case details | Manual |
| Claimed By | Your name | Manual |
| Status | passed/failed | Manual or Automated |
| Actual Results | Observed behavior for failures | Manual |
| automation_status | PASS/FAIL | Automated only |
| automation_notes | Error messages | Automated only |
| last_run | Timestamp of last execution | Automated only |

### Summary Worksheet

The Summary worksheet tracks all test runs with:
- **timestamp**: When tests were executed
- **total_tests**: Total number of tests run
- **passed**: Number passing
- **failed**: Number failing
- **pass_rate**: Success percentage
- **total_time**: Execution duration
- **test_categories**: Which test worksheets were executed
- **test_list**: Detailed list of tests with their results

Latest test runs appear at the top for easy tracking.

**History Management:**
- The Summary worksheet automatically maintains a rolling history of the last **100 test runs**
- Older entries are automatically removed to keep the spreadsheet clean and responsive
- This provides approximately 3 months of history with daily testing
- No manual cleanup required!

## 5. Troubleshooting Automated Testing

### Authentication Errors
- Verify `GOOGLE_SHEETS_ID` environment variable is set
- Contact the test lead if you need service account access

### Tests Not Updating Spreadsheet
- Ensure you're using the `--google-sheets` flag
- Check that you have internet connectivity
- Verify the spreadsheet URL is accessible

### Column Not Found
- The plugin automatically creates missing columns
- Ensure the worksheet has a header row

## 6. Need Help?

If you have questions or encounter unclear steps, reach out to the test lead **Carolina Steadham** – the Guardian of Quality Realms. ⭐

### Additional Resources

- **Test Framework Documentation**: See `pytest_google_sheets.py` for plugin details
- **Slack Channel**: https://owasp.slack.com/archives/C09A2MFUXJ9
- **GitHub Issues**: https://github.com/GenAI-Security-Project/finbot-ctf/issues
