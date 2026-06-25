// ═══════════════════════════════════════════════════════════════
// AI QUALIZER — ADDITIONS TO EXISTING SCRIPT
// Paste this block at the bottom of your existing Code.gs,
// then replace your onOpen() with the one below.
// ═══════════════════════════════════════════════════════════════

// ── UPDATED MENU ─────────────────────────────────────────────────
// Replace your existing onOpen() with this one.
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu("AI Qualizer")
    .addSubMenu(ui.createMenu("Setup rubric")
      .addItem("Describe it in plain English (AI generates)", "setupRubricFromDescription")
      .addItem("Load a pre-built template", "promptAndLoadTemplate"))
    .addItem("Setup QA config", "setupQAConfig")
    .addItem("Setup report config", "setupReportConfig")
    .addSeparator()
    .addSubMenu(ui.createMenu("Pull from BigQuery")
      .addItem("Maven conversations (SMS / Chat / Voice)", "pullMavenConversations")
      .addItem("EPO Churn — Sales & Success", "pullEPOChurnTranscripts"))
    .addSeparator()
    .addItem("Step 1: Classify (dynamic rubric)", "classifyTranscriptsDynamic")
    .addItem("Step 1b: Validate values", "validateClassifications")
    .addItem("Step 2 (optional): Calibration round — 10 samples", "runCalibrationRound")
    .addItem("Step 3: Build QA Review tab", "buildQAReview")
    .addItem("Step 3b: Re-classify low confidence", "reclassifyLowConfidence")
    .addItem("Step 4: Generate report", "generateReport")
    .addSeparator()
    .addItem("Refresh dashboard", "buildDashboard")
    .addToUi();
}


// ═══════════════════════════════════════════════════════════════
// RUBRIC DESIGNER — plain English → AI-generated rubric
// ═══════════════════════════════════════════════════════════════

function setupRubricFromDescription() {
  const ui = SpreadsheetApp.getUi();
  const response = ui.prompt(
    "Rubric designer",
    "Describe what you want to find out in plain English.\n\n" +
    "Examples:\n" +
    "• Understand why newly onboarded pros churn within 28 days\n" +
    "• Identify why conversations escalated and what the AI failed to handle\n" +
    "• Surface key pain points from CSAT survey comments\n\n" +
    "Research question:",
    ui.ButtonSet.OK_CANCEL
  );
  if (response.getSelectedButton() !== ui.Button.OK) return;

  const description = response.getResponseText().trim();
  if (!description) return;

  ui.alert("Generating rubric... this takes ~10 seconds. Click OK and wait.");

  const prompt =
    "You are an expert qualitative research analyst at Thumbtack.\n" +
    "Turn this plain-English research question into a structured analysis rubric.\n\n" +
    "Rules:\n" +
    "- Generate 3–6 dimensions that together fully answer the research question\n" +
    "- Each dimension should be independently classifiable from the text alone\n" +
    "- Possible values should be mutually exclusive, exhaustive, and lowercase\n" +
    "- Always include 'unclear' or 'not applicable' as a fallback value where sensible\n" +
    "- Keep dimension names short (2–4 words), values even shorter (1–3 words)\n\n" +
    "Return ONLY a JSON array, no other text:\n" +
    '[{"dimension":"short name","values":["v1","v2"],"description":"one sentence"}]\n\n' +
    "Research question: " + description;

  let dimensions;
  try {
    const raw = callGeminiAPI(prompt, 0.3);
    const cleaned = raw.replace(/```json\n?/g, "").replace(/```\n?/g, "").trim();
    dimensions = JSON.parse(cleaned);
  } catch (e) {
    ui.alert("Could not generate rubric: " + e.message);
    return;
  }

  _writeRubricToSheet(dimensions);
  ui.alert(
    "Rubric generated! " + dimensions.length + " dimensions written to the Rubric tab.\n\n" +
    "Review and edit the Rubric tab, then run Step 1 to classify."
  );
}


// ═══════════════════════════════════════════════════════════════
// RUBRIC TEMPLATES
// ═══════════════════════════════════════════════════════════════

const RUBRIC_TEMPLATES = {
  "Contact Driver": [
    { dimension: "Contact Driver", values: ["billing / charges","account issue","lead quality","technical issue","policy question","dispute / refund","general inquiry","other"], description: "The primary reason the customer or pro reached out." },
    { dimension: "User Type", values: ["customer","pro","unclear"], description: "Whether the contact came from a customer or a pro." },
    { dimension: "Resolution", values: ["resolved","escalated","unresolved","unclear"], description: "Whether the issue was resolved during the interaction." },
    { dimension: "Sentiment", values: ["positive","neutral","frustrated","angry"], description: "Overall emotional tone of the contact." },
  ],
  "Escalation Patterns": [
    { dimension: "Escalation Trigger", values: ["explicit request","repeated misunderstanding","complex issue","emotional distress","policy limitation","technical failure","unclear"], description: "What caused the conversation to escalate to a human agent." },
    { dimension: "AI Failure Mode", values: ["wrong answer","loop / repetition","missing knowledge","tone mismatch","no failure","unclear"], description: "How the AI bot fell short before escalation." },
    { dimension: "Issue Category", values: ["billing","account","leads","reviews","technical","policy","other"], description: "The subject matter of the escalated conversation." },
    { dimension: "Avoidable", values: ["yes","no","unclear"], description: "Whether the escalation could have been prevented." },
  ],
  "CSAT Pain Points": [
    { dimension: "Primary Theme", values: ["pricing","lead quality","customer service","product / ux","pro quality","communication","billing","other"], description: "The main topic the respondent is commenting on." },
    { dimension: "Sentiment", values: ["positive","negative","mixed","neutral"], description: "The overall tone of the feedback." },
    { dimension: "Actionability", values: ["specific and actionable","vague","praise only","unclear"], description: "How actionable the feedback is for the product or ops team." },
  ],
  "Thumbtack Numbers": [
    { dimension: "Numbers Discussed", values: ["yes","no","unclear"], description: "Whether any specific Thumbtack numbers were mentioned." },
    { dimension: "Number Type", values: ["lead pricing","credits / refunds","account stats","platform metrics","not applicable"], description: "What category of numbers came up." },
    { dimension: "Customer Reaction", values: ["accepted","disputed","confused","not applicable"], description: "How the customer responded to the numbers discussed." },
  ],
  "Feature Mentions": [
    { dimension: "Feature Area", values: ["leads / targeting","payments","reviews","profile","messaging","background check","app / technical","other","none"], description: "The Thumbtack product area mentioned in the conversation." },
    { dimension: "Mention Type", values: ["complaint","question","praise","informational","not applicable"], description: "How the feature was brought up." },
    { dimension: "Outcome", values: ["resolved","referred to help center","escalated","not applicable"], description: "How the feature-related discussion was handled." },
  ],
  "EPO Churn Analysis": [
    { dimension: "Churn Signal", values: ["explicit intent to leave","dissatisfaction expressed","disengaged / unresponsive","positive / interested","neutral","unclear"], description: "Whether the transcript contains language or behavior that predicts churn." },
    { dimension: "Primary Concern", values: ["lead quality / quantity","pricing / credits","not enough work","platform confusion","competition / alternatives","no concern raised","other"], description: "The main concern or objection the pro raised during the EPO interaction." },
    { dimension: "Rep Action", values: ["addressed concern effectively","offered support / resources","scheduled follow-up","closed / converted","no meaningful action","could not reach pro"], description: "What the Sales & Success rep did to address the pro's situation." },
    { dimension: "Pro Engagement", values: ["high — full conversation","medium — partial engagement","low — brief / distracted","no contact"], description: "How engaged the pro was during the EPO interaction." },
  ],
};

function promptAndLoadTemplate() {
  const ui = SpreadsheetApp.getUi();
  const names = Object.keys(RUBRIC_TEMPLATES);
  const response = ui.prompt(
    "Load rubric template",
    "Available templates:\n" + names.map((n, i) => `${i + 1}. ${n}`).join("\n") +
    "\n\nType the template name exactly (or number):",
    ui.ButtonSet.OK_CANCEL
  );
  if (response.getSelectedButton() !== ui.Button.OK) return;

  const input = response.getResponseText().trim();
  let templateName = RUBRIC_TEMPLATES[input]
    ? input
    : names[parseInt(input) - 1];

  if (!templateName || !RUBRIC_TEMPLATES[templateName]) {
    ui.alert("Template not found. Available: " + names.join(", "));
    return;
  }

  _writeRubricToSheet(RUBRIC_TEMPLATES[templateName]);
  ui.alert("Template loaded: " + templateName + "\n\nRubric tab updated. Run Step 1 to classify.");
}

// Writes an array of {dimension, values, description} to the Rubric tab.
function _writeRubricToSheet(dimensions) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let rubricSheet = ss.getSheetByName(SHEET_RUBRIC);
  if (!rubricSheet) {
    rubricSheet = ss.insertSheet(SHEET_RUBRIC);
  } else {
    rubricSheet.clearContents();
    rubricSheet.clearFormats();
  }

  const headers = ["Dimension Name", "Possible Values (comma-separated)", "What This Measures", "Active?"];
  rubricSheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  rubricSheet.getRange(1, 1, 1, headers.length)
    .setBackground("#1a3a5c").setFontColor("white").setFontWeight("bold");

  const rows = dimensions.map(d => [
    d.dimension,
    Array.isArray(d.values) ? d.values.join(", ") : d.values,
    d.description,
    "yes"
  ]);
  rubricSheet.getRange(2, 1, rows.length, headers.length).setValues(rows);

  // Dropdown for Active?
  const activeRange = rubricSheet.getRange(2, 4, rows.length, 1);
  activeRange.setDataValidation(
    SpreadsheetApp.newDataValidation().requireValueInList(["yes", "no"]).build()
  );

  rubricSheet.autoResizeColumn(1);
  rubricSheet.autoResizeColumn(2);
  rubricSheet.setColumnWidth(3, 320);
  rubricSheet.setColumnWidth(4, 80);
}


// ═══════════════════════════════════════════════════════════════
// DYNAMIC CLASSIFY — works with any rubric, not just escalation
// ═══════════════════════════════════════════════════════════════

// Reads dimensions from the Rubric tab.
// Returns [{name, values (array), description, fieldKey (snake_case)}]
function getDimensionsFromRubric() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const rubricSheet = ss.getSheetByName(SHEET_RUBRIC);
  if (!rubricSheet) throw new Error("No Rubric tab found. Set up your rubric first.");

  const data = rubricSheet.getDataRange().getValues();
  const headers = data[0].map(h => (h || "").toString().toLowerCase());

  // Support both old format and new format
  const dimIdx    = Math.max(headers.indexOf("dimension name"), headers.indexOf("dimension"), 0);
  const valIdx    = Math.max(headers.indexOf("possible values (comma-separated)"), headers.indexOf("values"), 1);
  const descIdx   = Math.max(headers.indexOf("what this measures"), headers.indexOf("description"), 2);
  const activeIdx = Math.max(headers.indexOf("active?"), headers.indexOf("active"), 3);

  const dimensions = [];
  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    const name   = (row[dimIdx]    || "").toString().trim();
    const vals   = (row[valIdx]    || "").toString();
    const desc   = (row[descIdx]   || "").toString().trim();
    const active = (row[activeIdx] || "yes").toString().toLowerCase();
    if (!name || active === "no") continue;
    dimensions.push({
      name,
      values: vals.split(",").map(v => v.trim().toLowerCase()).filter(v => v),
      description: desc,
      fieldKey: name.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, ""),
    });
  }
  return dimensions;
}

// Dynamic version of classifyTranscripts — reads dimensions from Rubric tab
// and creates/writes to columns named after each dimension.
function classifyTranscriptsDynamic() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const transcriptSheet = ss.getSheetByName(SHEET_TRANSCRIPTS);
  if (!transcriptSheet) {
    SpreadsheetApp.getUi().alert("No Transcripts tab found.");
    return;
  }

  let dimensions;
  try {
    dimensions = getDimensionsFromRubric();
  } catch (e) {
    SpreadsheetApp.getUi().alert(e.message);
    return;
  }
  if (dimensions.length === 0) {
    SpreadsheetApp.getUi().alert("Rubric has no active dimensions. Check the Rubric tab.");
    return;
  }

  // Build rubric prompt context
  let rubricContext = "CLASSIFICATION RUBRIC:\n\n";
  dimensions.forEach(d => {
    rubricContext += `${d.name}:\n  Values: ${d.values.join(", ")}\n  Description: ${d.description}\n\n`;
  });

  // Strict constraint block
  rubricContext += "\n────────────────────────────────────────\n";
  rubricContext += "STRICT OUTPUT CONSTRAINTS — use ONLY these exact values:\n";
  dimensions.forEach(d => {
    rubricContext += `  • ${d.fieldKey}: ${d.values.join(", ")}\n`;
  });
  rubricContext += "  • confidence: high, medium, low\n";
  rubricContext += "  • ai_notes: one sentence explaining the classification\n";
  rubricContext += "────────────────────────────────────────\n\n";

  // Get/create columns for each dimension + standard columns
  const data = transcriptSheet.getDataRange().getValues();
  const headers = [...data[0]];

  const colTranscript  = _findCol(headers, ["transcript","conversation","chat","body","message","text"]);
  const colSummary     = _findCol(headers, ["user request summary","summary","request","description"]);
  const colDate        = _findCol(headers, ["date","created","timestamp"]);

  // Find or create a column for each dimension + Confidence + AI Notes + Value Check
  const outputCols = {};
  [...dimensions.map(d => d.name), "Confidence", "AI Notes", "Value Check"].forEach(colName => {
    let idx = headers.indexOf(colName);
    if (idx === -1) {
      idx = headers.length;
      transcriptSheet.getRange(1, idx + 1).setValue(colName)
        .setBackground("#1a3a5c").setFontColor("white").setFontWeight("bold");
      headers.push(colName);
    }
    outputCols[colName] = idx;
  });

  const allowedMap = {};
  dimensions.forEach(d => { allowedMap[d.fieldKey] = d.values; });

  // Check for golden set examples to inject
  const exampleBlock = _buildGoldenExamplesBlock();

  let classified = 0, skipped = 0;

  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    const firstDimCol = outputCols[dimensions[0].name];

    // Skip already classified rows
    if (row[firstDimCol] && row[firstDimCol] !== "") { skipped++; continue; }

    const transcript = colTranscript >= 0 ? (row[colTranscript] || "") : "";
    const summary    = colSummary >= 0    ? (row[colSummary]    || "") : "";
    if (!transcript && !summary) continue;

    try {
      const result = _classifyRowDynamic(rubricContext, dimensions, exampleBlock, transcript, summary);

      // Write each dimension's value
      dimensions.forEach(d => {
        const val = result[d.fieldKey] || "";
        transcriptSheet.getRange(i + 1, outputCols[d.name] + 1).setValue(val);
      });
      transcriptSheet.getRange(i + 1, outputCols["Confidence"] + 1).setValue(result.confidence || "");
      transcriptSheet.getRange(i + 1, outputCols["AI Notes"]  + 1).setValue(result.ai_notes   || "");

      // Value check
      const issues = [];
      dimensions.forEach(d => {
        const val = (result[d.fieldKey] || "").toLowerCase();
        if (val && !d.values.includes(val)) issues.push(`${d.name}="${result[d.fieldKey]}"`);
      });
      const checkResult = issues.length === 0 ? "OK" : "INVALID: " + issues.join(", ");
      const checkCell = transcriptSheet.getRange(i + 1, outputCols["Value Check"] + 1);
      checkCell.setValue(checkResult).setBackground(issues.length === 0 ? "#d4edda" : "#f8d7da");

      classified++;
      Utilities.sleep(500);
    } catch (e) {
      Logger.log("Row " + (i + 1) + " error: " + e.message);
    }
  }

  SpreadsheetApp.getUi().alert(
    "Classification complete!\n\n" + classified + " rows classified\n" + skipped + " rows already done"
  );
}

function _classifyRowDynamic(rubricContext, dimensions, exampleBlock, transcript, summary) {
  const jsonFields = [...dimensions.map(d => `"${d.fieldKey}"`), '"confidence"', '"ai_notes"'].join(", ");
  const prompt =
    rubricContext +
    (exampleBlock ? "\nHUMAN-VALIDATED EXAMPLES:\n" + exampleBlock + "\n\n" : "") +
    "Classify this text using the rubric above.\n" +
    "Return ONLY a JSON object with these fields: " + jsonFields + "\n" +
    "Use ONLY the exact values from the STRICT OUTPUT CONSTRAINTS. No paraphrasing.\n\n" +
    "TEXT:\n" +
    (summary ? "Summary: " + summary + "\n" : "") +
    "Content: " + transcript.substring(0, 3000) + "\n\n" +
    "Return ONLY valid JSON, no other text.";

  const raw = callGeminiAPI(prompt, 0.1);
  const cleaned = raw.replace(/```json\n?/g, "").replace(/```\n?/g, "").trim();
  return JSON.parse(cleaned);
}

// Finds the first column index whose header matches any of the given keywords (case-insensitive).
function _findCol(headers, keywords) {
  for (let i = 0; i < headers.length; i++) {
    const h = (headers[i] || "").toString().toLowerCase();
    for (const kw of keywords) {
      if (h.includes(kw)) return i;
    }
  }
  return -1;
}

// Reads golden set examples from the Golden Set tab (if it exists).
// Returns a formatted string block, or empty string if none.
function _buildGoldenExamplesBlock() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const gsSheet = ss.getSheetByName("Golden Set");
  if (!gsSheet) return "";

  const data = gsSheet.getDataRange().getValues();
  if (data.length < 2) return "";

  const headers = data[0].map(h => (h || "").toString().toLowerCase());
  const colText   = _findCol(headers, ["transcript","text","content","conversation"]);
  const colSummary = _findCol(headers, ["summary","request","description"]);

  const examples = [];
  for (let i = 1; i < data.length && examples.length < 10; i++) {
    const row = data[i];
    const text    = colText    >= 0 ? (row[colText]    || "") : "";
    const summary = colSummary >= 0 ? (row[colSummary] || "") : "";
    // Collect all other columns as classification fields
    const fields = [];
    for (let j = 0; j < headers.length; j++) {
      if (j === colText || j === colSummary) continue;
      if (row[j]) fields.push(headers[j] + '="' + row[j] + '"');
    }
    if (text || summary) {
      examples.push(
        "Example " + (i) + ":\n" +
        (summary ? "  Summary: " + summary + "\n" : "") +
        (text ? "  Text: " + text.substring(0, 300) + "\n" : "") +
        "  Classification: " + fields.join(", ")
      );
    }
  }
  return examples.join("\n\n");
}


// ═══════════════════════════════════════════════════════════════
// CALIBRATION ROUND — 10 samples before full classify
// ═══════════════════════════════════════════════════════════════

// Runs a mini-classify on 10 random rows, writes results to a
// "Calibration" sheet for human review. Approved rows are saved
// to the "Golden Set" sheet to improve the full run.
function runCalibrationRound() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const transcriptSheet = ss.getSheetByName(SHEET_TRANSCRIPTS);

  let dimensions;
  try {
    dimensions = getDimensionsFromRubric();
  } catch (e) {
    SpreadsheetApp.getUi().alert(e.message);
    return;
  }

  let rubricContext = "CLASSIFICATION RUBRIC:\n\n";
  dimensions.forEach(d => {
    rubricContext += `${d.name}:\n  Values: ${d.values.join(", ")}\n  Description: ${d.description}\n\n`;
  });
  rubricContext += "\nSTRICT OUTPUT CONSTRAINTS:\n";
  dimensions.forEach(d => {
    rubricContext += `  • ${d.fieldKey}: ${d.values.join(", ")}\n`;
  });
  rubricContext += "  • confidence: high, medium, low\n  • ai_notes: one sentence\n\n";

  const data = transcriptSheet.getDataRange().getValues();
  const headers = data[0];
  const colTranscript = _findCol(headers, ["transcript","conversation","chat","body","message","text"]);
  const colSummary    = _findCol(headers, ["user request summary","summary","request","description"]);
  const colDate       = _findCol(headers, ["date","created","timestamp"]);

  // Sample 10 rows randomly
  const candidates = [];
  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    const text = colTranscript >= 0 ? row[colTranscript] : "";
    if (text) candidates.push({ rowNum: i + 1, row });
  }
  if (candidates.length === 0) {
    SpreadsheetApp.getUi().alert("No rows with transcript content found.");
    return;
  }
  const sample = candidates.sort(() => Math.random() - 0.5).slice(0, 10);

  // Create / clear Calibration tab
  let calibSheet = ss.getSheetByName("Calibration");
  if (!calibSheet) {
    calibSheet = ss.insertSheet("Calibration");
  } else {
    calibSheet.clearContents();
    calibSheet.clearFormats();
  }

  const calibHeaders = [
    "Row #", "Date", "Text preview",
    ...dimensions.map(d => d.name),
    "Confidence", "AI Notes",
    "Approve? (yes/no)", "Notes"
  ];
  calibSheet.getRange(1, 1, 1, calibHeaders.length).setValues([calibHeaders]);
  calibSheet.getRange(1, 1, 1, calibHeaders.length)
    .setBackground("#1a3a5c").setFontColor("white").setFontWeight("bold");

  const rows = [];
  for (const { rowNum, row } of sample) {
    const transcript = colTranscript >= 0 ? (row[colTranscript] || "") : "";
    const summary    = colSummary >= 0    ? (row[colSummary]    || "") : "";
    const date       = colDate >= 0       ? (row[colDate]       || "") : "";
    try {
      const result = _classifyRowDynamic(rubricContext, dimensions, "", transcript, summary);
      rows.push([
        rowNum,
        date,
        transcript.substring(0, 150) + "...",
        ...dimensions.map(d => result[d.fieldKey] || ""),
        result.confidence || "",
        result.ai_notes || "",
        "yes",
        ""
      ]);
      Utilities.sleep(500);
    } catch (e) {
      rows.push([rowNum, date, transcript.substring(0, 150) + "...", ...dimensions.map(() => "ERROR"), "", e.message, "no", ""]);
    }
  }

  if (rows.length > 0) {
    calibSheet.getRange(2, 1, rows.length, calibHeaders.length).setValues(rows);
    const approveCol = 4 + dimensions.length; // "Approve?" column
    const approveRange = calibSheet.getRange(2, approveCol, rows.length, 1);
    approveRange.setDataValidation(
      SpreadsheetApp.newDataValidation().requireValueInList(["yes", "no"]).build()
    );
    calibSheet.autoResizeColumns(1, calibHeaders.length);
  }

  SpreadsheetApp.getUi().alert(
    "Calibration round complete!\n\n" +
    rows.length + " samples classified and written to the Calibration tab.\n\n" +
    "Review each row — change 'yes' to 'no' for any you disagree with.\n" +
    "Then run 'Save approved calibration examples' from the menu to inject them into the full run."
  );
}

// Saves approved calibration rows to the Golden Set tab.
// Run this after reviewing the Calibration tab.
function saveCalibrationExamples() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const calibSheet = ss.getSheetByName("Calibration");
  if (!calibSheet) {
    SpreadsheetApp.getUi().alert("No Calibration tab found. Run the calibration round first.");
    return;
  }

  const data = calibSheet.getDataRange().getValues();
  const headers = data[0].map(h => (h || "").toString());

  const approveIdx = headers.indexOf("Approve? (yes/no)");
  const textIdx    = headers.indexOf("Text preview");
  const notesIdx   = headers.indexOf("AI Notes");

  // Get or create Golden Set tab
  let gsSheet = ss.getSheetByName("Golden Set");
  if (!gsSheet) {
    gsSheet = ss.insertSheet("Golden Set");
    gsSheet.getRange(1, 1, 1, headers.length - 1).setValues([headers.slice(0, -1)]);
    gsSheet.getRange(1, 1, 1, headers.length - 1)
      .setBackground("#1a3a5c").setFontColor("white").setFontWeight("bold");
  }

  const existing = gsSheet.getDataRange().getValues().slice(1).map(r => r[textIdx] || "");
  let added = 0;

  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    const approve = (row[approveIdx] || "").toString().toLowerCase();
    if (approve !== "yes") continue;
    const text = row[textIdx] || "";
    if (existing.includes(text)) continue; // deduplicate

    gsSheet.appendRow(row.slice(0, -1)); // exclude the "Notes" column
    added++;
  }

  SpreadsheetApp.getUi().alert(
    added + " examples saved to the Golden Set tab.\n\n" +
    "These will be injected automatically when you run Step 1 (Classify)."
  );
}


// ═══════════════════════════════════════════════════════════════
// BIGQUERY CONNECTOR — Maven + EPO Churn
// ═══════════════════════════════════════════════════════════════

const BQ_PROJECT = "tt-dp-prod";
const BQ_QUERY_URL = "https://bigquery.googleapis.com/bigquery/v2/projects/" + BQ_PROJECT + "/queries";

function _runBQQuery(sql) {
  const payload = {
    query: sql,
    useLegacySql: false,
    timeoutMs: 90000,
    location: "US"
  };
  const options = {
    method: "post",
    contentType: "application/json",
    headers: { Authorization: "Bearer " + ScriptApp.getOAuthToken() },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };
  const res = JSON.parse(UrlFetchApp.fetch(BQ_QUERY_URL, options).getContentText());
  if (res.error) throw new Error("BigQuery error: " + JSON.stringify(res.error));
  if (!res.jobComplete) throw new Error("BigQuery job timed out. Try a smaller date range or lower row limit.");

  const fields = (res.schema || {}).fields || [];
  const fieldNames = fields.map(f => f.name);
  return (res.rows || []).map(row =>
    Object.fromEntries(row.f.map((cell, i) => [fieldNames[i], cell.v]))
  );
}

// Writes an array of row objects to the Transcripts tab.
// Creates the tab if it doesn't exist; overwrites if it does.
function _writeRowsToTranscripts(rows, extraMeta) {
  if (!rows || rows.length === 0) {
    SpreadsheetApp.getUi().alert("No rows returned. Try adjusting the filters.");
    return;
  }
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_TRANSCRIPTS);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_TRANSCRIPTS);
  } else {
    const proceed = SpreadsheetApp.getUi().alert(
      "This will overwrite the existing Transcripts tab (" +
      (sheet.getLastRow() - 1) + " rows). Proceed?",
      SpreadsheetApp.getUi().ButtonSet.YES_NO
    );
    if (proceed !== SpreadsheetApp.getUi().Button.YES) return;
    sheet.clearContents();
  }

  const allKeys = Object.keys(rows[0]);
  sheet.getRange(1, 1, 1, allKeys.length).setValues([allKeys]);
  sheet.getRange(1, 1, 1, allKeys.length)
    .setBackground("#1a3a5c").setFontColor("white").setFontWeight("bold");

  const values = rows.map(r => allKeys.map(k => r[k] || ""));
  sheet.getRange(2, 1, values.length, allKeys.length).setValues(values);
  sheet.autoResizeColumns(1, allKeys.length);
}

// ── Maven conversations pull ─────────────────────────────────────
function pullMavenConversations() {
  const ui = SpreadsheetApp.getUi();

  const channelRes = ui.prompt(
    "Maven: Channel",
    "Channel to pull (type 'all', 'chat', 'sms', or 'voice'):",
    ui.ButtonSet.OK_CANCEL
  );
  if (channelRes.getSelectedButton() !== ui.Button.OK) return;
  const channel = channelRes.getResponseText().trim() || "all";

  const dateRes = ui.prompt(
    "Maven: Date range",
    "Start date (YYYY-MM-DD):",
    ui.ButtonSet.OK_CANCEL
  );
  if (dateRes.getSelectedButton() !== ui.Button.OK) return;
  const startDate = dateRes.getResponseText().trim();

  const endRes = ui.prompt(
    "Maven: Date range",
    "End date (YYYY-MM-DD):",
    ui.ButtonSet.OK_CANCEL
  );
  if (endRes.getSelectedButton() !== ui.Button.OK) return;
  const endDate = endRes.getResponseText().trim();

  const limitRes = ui.prompt(
    "Maven: Row limit",
    "Max rows to pull (recommended: 100–500):",
    ui.ButtonSet.OK_CANCEL
  );
  if (limitRes.getSelectedButton() !== ui.Button.OK) return;
  const limit = Math.min(parseInt(limitRes.getResponseText().trim()) || 300, 2000);

  const channelFilter = channel !== "all" ? "AND c.channel = '" + channel + "'" : "";

  const sql =
    "WITH msg_concat AS (\n" +
    "  SELECT m.conversation_reference_id,\n" +
    "    STRING_AGG(\n" +
    "      CASE WHEN m.message_type = 'bot' THEN CONCAT('Bot: ', COALESCE(m.bot_response_text,''))\n" +
    "           ELSE CONCAT('User: ', COALESCE(m.message_text,'')) END,\n" +
    "      '\\n' ORDER BY m.message_index\n" +
    "    ) AS transcript_text\n" +
    "  FROM `tt-dp-prod.maven.messages` m\n" +
    "  WHERE m.created_date BETWEEN '" + startDate + "' AND '" + endDate + "'\n" +
    "  GROUP BY m.conversation_reference_id\n" +
    ")\n" +
    "SELECT\n" +
    "  c.created_date AS Date,\n" +
    "  COALESCE(mc.transcript_text, '') AS Transcript,\n" +
    "  c.user_request_summary AS `User Request Summary`,\n" +
    "  c.channel,\n" +
    "  c.resolution_status_summary AS resolution_status,\n" +
    "  c.sentiment,\n" +
    "  CAST(c.was_actual_escalated AS STRING) AS was_escalated,\n" +
    "  c.conversation_reference_id AS conversation_id\n" +
    "FROM `tt-dp-prod.maven.conversations` c\n" +
    "LEFT JOIN msg_concat mc ON c.conversation_reference_id = mc.conversation_reference_id\n" +
    "WHERE c.created_date BETWEEN '" + startDate + "' AND '" + endDate + "'\n" +
    channelFilter + "\n" +
    "ORDER BY c.created_date DESC\n" +
    "LIMIT " + limit;

  ui.alert("Pulling from BigQuery... click OK and wait (~15–30 seconds).");
  try {
    const rows = _runBQQuery(sql);
    _writeRowsToTranscripts(rows);
    ui.alert("Done! " + rows.length + " Maven conversations written to the Transcripts tab.");
  } catch (e) {
    ui.alert("BigQuery error: " + e.message +
      "\n\nMake sure you're signed into the correct Google account and have tt-dp-prod access.");
  }
}

// ── EPO Churn pull ───────────────────────────────────────────────
function pullEPOChurnTranscripts() {
  const ui = SpreadsheetApp.getUi();

  const windowRes = ui.prompt(
    "EPO Churn: Churn window",
    "Which churn window? Type '28d' or '60d':",
    ui.ButtonSet.OK_CANCEL
  );
  if (windowRes.getSelectedButton() !== ui.Button.OK) return;
  const churnWindow = windowRes.getResponseText().trim() === "60d" ? "60d" : "28d";
  const churnCol = churnWindow === "28d" ? "churned_within_28d" : "churned_within_60d";

  const outcomeRes = ui.prompt(
    "EPO Churn: Outcome filter",
    "Which pros to include?\n1 = All pros\n2 = Churned only\n3 = Retained only\n\nType 1, 2, or 3:",
    ui.ButtonSet.OK_CANCEL
  );
  if (outcomeRes.getSelectedButton() !== ui.Button.OK) return;
  const outcomeChoice = outcomeRes.getResponseText().trim();
  let churnFilter = "";
  if (outcomeChoice === "2") churnFilter = "AND CAST(" + churnCol + " AS STRING) = 'true'";
  else if (outcomeChoice === "3") churnFilter = "AND CAST(" + churnCol + " AS STRING) = 'false'";

  const limitRes = ui.prompt(
    "EPO Churn: Row limit",
    "Max pros to pull (max 1,500 per Jeanne's methodology):",
    ui.ButtonSet.OK_CANCEL
  );
  if (limitRes.getSelectedButton() !== ui.Button.OK) return;
  const limit = Math.min(parseInt(limitRes.getResponseText().trim()) || 300, 1500);

  const EPO_CALLS   = "tt-dp-prod.sandbox.jas_epo_calls_disposition_churn_20260623";
  const EPO_JOURNEY = "tt-dp-prod.sandbox.jas_epo_pro_journey_20260623";

  const sql =
    "WITH pro_sample AS (\n" +
    "  SELECT\n" +
    "    CAST(pro_user_pk AS STRING) AS pro_id,\n" +
    "    ANY_VALUE(CAST(" + churnCol + " AS STRING)) AS churned_28d,\n" +
    "    ANY_VALUE(CAST(churned_within_60d AS STRING)) AS churned_60d,\n" +
    "    STRING_AGG(DISTINCT task_disposition ORDER BY task_disposition) AS task_disposition,\n" +
    "    ANY_VALUE(call_outcome_bucket) AS call_outcome_bucket\n" +
    "  FROM `" + EPO_CALLS + "`\n" +
    "  WHERE engaged_at_call = TRUE\n" +
    "    AND churn_28d_resolved = TRUE\n" +
    "    " + churnFilter + "\n" +
    "  GROUP BY pro_user_pk\n" +
    "  LIMIT " + limit + "\n" +
    ")\n" +
    "SELECT\n" +
    "  j.first_call_date AS Date,\n" +
    "  j.journey_transcript AS Transcript,\n" +
    "  CONCAT(\n" +
    "    'Disposition: ', COALESCE(ps.task_disposition,'unknown'),\n" +
    "    ' | Churn 28d: ', COALESCE(ps.churned_28d,'?'),\n" +
    "    ' | Status: ', COALESCE(j.action_plan_status,'unknown')\n" +
    "  ) AS `User Request Summary`,\n" +
    "  ps.pro_id AS pro_user_pk,\n" +
    "  j.action_plan_status,\n" +
    "  CAST(j.n_calls AS STRING) AS n_calls,\n" +
    "  ps.churned_28d,\n" +
    "  ps.churned_60d,\n" +
    "  ps.task_disposition,\n" +
    "  ps.call_outcome_bucket\n" +
    "FROM pro_sample ps\n" +
    "JOIN `" + EPO_JOURNEY + "` j ON ps.pro_id = CAST(j.pro_user_pk AS STRING)\n" +
    "WHERE j.journey_transcript IS NOT NULL\n" +
    "  AND TRIM(j.journey_transcript) != ''\n" +
    "ORDER BY j.first_call_date DESC\n" +
    "LIMIT " + limit;

  ui.alert("Pulling EPO transcripts from BigQuery... click OK and wait (~20–40 seconds).");
  try {
    const rows = _runBQQuery(sql);
    _writeRowsToTranscripts(rows);

    const churned  = rows.filter(r => r.churned_28d === "true").length;
    const retained = rows.filter(r => r.churned_28d === "false").length;
    ui.alert(
      "Done! " + rows.length + " EPO pro transcripts written to the Transcripts tab.\n\n" +
      "Churned (28d): " + churned + "\nRetained (28d): " + retained
    );
  } catch (e) {
    ui.alert("BigQuery error: " + e.message +
      "\n\nMake sure you have access to tt-dp-prod.sandbox tables.");
  }
}
