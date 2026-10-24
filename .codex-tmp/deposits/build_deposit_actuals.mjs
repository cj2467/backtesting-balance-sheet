import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "/Users/cjwork/holodeck-archive";
const controlledPath = path.join(root, "outputs", "01a0a8d5-e41c-7cd1-8fca-c36962c30d1e", "balance-rate-nii-cof-monthly-controlled.xlsx");
const sourceJsonPath = path.join(root, ".codex-tmp", "deposits", "deposit_sources.json");
const outputDir = path.join(root, "outputs", "01a16ceb-c159-7730-bbe3-625a9d549397");
const outputPath = path.join(outputDir, "deposit-rate-balance-actuals-2024-h1-2026.xlsx");
const previewDir = path.join(root, ".codex-tmp", "deposits", "previews");

const sourceData = JSON.parse(await fs.readFile(sourceJsonPath, "utf8"));
const controlled = await SpreadsheetFile.importXlsx(await FileBlob.load(controlledPath));
controlled.recalculate();

function excelSerialToDate(serial) {
  return new Date(Date.UTC(1899, 11, 30) + Number(serial) * 86400000);
}

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function monthKey(date) {
  return date.toISOString().slice(0, 7);
}

function quarterOf(date) {
  return Math.floor(date.getUTCMonth() / 3) + 1;
}

function periodOf(date) {
  return `${date.getUTCFullYear()}Q${quarterOf(date)}`;
}

function previousQuarterEnd(year, quarter) {
  if (quarter === 1) return `${year - 1}-12-31`;
  return new Date(Date.UTC(year, (quarter - 1) * 3, 0)).toISOString().slice(0, 10);
}

function currentQuarterEnd(year, quarter) {
  return new Date(Date.UTC(year, quarter * 3, 0)).toISOString().slice(0, 10);
}

const avgSheet = controlled.worksheets.getItem("Monthly Avg Balance");
const expenseSheet = controlled.worksheets.getItem("Monthly NII");
const rateSheet = controlled.worksheets.getItem("Monthly Rate");
const rawDates = avgSheet.getRange("B4:AQ4").values[0];
const rawBalances = avgSheet.getRange("B15:AQ15").values[0];
const rawExpenses = expenseSheet.getRange("B15:AQ15").values[0];
const rawRates = rateSheet.getRange("B15:AQ15").values[0];

const monthlyControls = rawDates.map((value, index) => {
  const date = value instanceof Date ? value : excelSerialToDate(value);
  return {
    month: date,
    monthKey: monthKey(date),
    year: date.getUTCFullYear(),
    quarter: quarterOf(date),
    period: periodOf(date),
    totalIbBalance: Number(rawBalances[index]),
    totalIbExpense: Number(rawExpenses[index]),
    totalIbRate: Number(rawRates[index]),
  };
}).filter((row) => row.monthKey >= "2024-01" && row.monthKey <= "2026-06");

if (monthlyControls.length !== 30) {
  throw new Error(`Expected 30 monthly controls; found ${monthlyControls.length}`);
}

const disclosureOrder = [
  "Checking",
  "Savings",
  "Time deposits",
  "Total interest-bearing deposits",
  "Non-interest-bearing deposits",
];
const outputOrder = [...disclosureOrder, "Total deposits"];
const quarterIndex = new Map(sourceData.quarterly.map((row) => [`${row.period}|${row.deposit_type}`, row]));
const anchorIndex = new Map(sourceData.noninterest_eop_anchors.map((row) => [row.period_end, row]));

for (const control of monthlyControls) {
  for (const depositType of disclosureOrder) {
    if (!quarterIndex.has(`${control.period}|${depositType}`)) {
      throw new Error(`Missing quarterly disclosure: ${control.period} / ${depositType}`);
    }
  }
}

const workbook = Workbook.create();
const output = workbook.worksheets.add("Deposit Actuals");
const sources = workbook.worksheets.add("Sources & Checks");
output.showGridLines = false;
sources.showGridLines = false;
output.tabColor = "#003B70";
sources.tabColor = "#C41230";

const fontName = "Arial";
const dark = "#003B70";
const blue = "#0072CE";
const red = "#C41230";
const mid = "#66788A";
const light = "#DCE6F1";
const lighter = "#F4F7FA";
const totalFill = "#E8F0F7";
const white = "#FFFFFF";
const black = "#000000";
const errorFill = "#FCE4D6";
const errorText = "#9C0006";

function setDarkHeader(range) {
  range.format = {
    fill: dark,
    font: { name: fontName, size: 10, bold: true, color: white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: white },
  };
}

function setSectionTitle(range) {
  range.format = {
    fill: light,
    font: { name: fontName, size: 10, bold: true, color: dark },
    borders: {
      left: { style: "medium", color: red },
      bottom: { style: "thin", color: dark },
    },
  };
}

// Sources: quarterly disclosures.
sources.getRange("A2").values = [["Deposit rate and balance sources"]];
sources.getRange("A2").format.font = { name: fontName, size: 14, bold: true, color: dark };
sources.getRange("A3:H3").merge();
sources.getRange("A3").values = [["Quarterly average balances and interest expense come from Capital One filings. Monthly interest-bearing totals come from the controlled workbook."]];
sources.getRange("A3").format.font = { name: fontName, size: 9, italic: true, color: mid };
sources.getRange("A3:R3").format.borders = { bottom: { style: "medium", color: red } };

const quarterlyHeaders = [[
  "Source Period",
  "Deposit Type",
  "Reported Average Balance ($mm)",
  "Reported Interest Expense ($mm)",
  "Reported Average Rate",
  "Effective Rate",
  "Share of Interest-Bearing Balance",
  "Disclosure Basis",
]];
sources.getRange("A5:H5").values = quarterlyHeaders;
setDarkHeader(sources.getRange("A5:H5"));

const quarterlyRows = [...sourceData.quarterly].sort((a, b) => {
  const p = a.period.localeCompare(b.period);
  return p || disclosureOrder.indexOf(a.deposit_type) - disclosureOrder.indexOf(b.deposit_type);
});
const quarterlyStart = 6;
const quarterlyEnd = quarterlyStart + quarterlyRows.length - 1;
const quarterlyValues = quarterlyRows.map((row) => [
  row.period,
  row.deposit_type,
  row.avg_balance_mm,
  row.interest_expense_mm,
  row.reported_rate,
  null,
  null,
  row.method,
]);
sources.getRange(`A${quarterlyStart}:H${quarterlyEnd}`).values = quarterlyValues;

const quarterlyRowMap = new Map();
quarterlyRows.forEach((row, index) => quarterlyRowMap.set(`${row.period}|${row.deposit_type}`, quarterlyStart + index));
const effectiveRateFormulas = [];
const shareFormulas = [];
for (let row = quarterlyStart; row <= quarterlyEnd; row += 1) {
  const item = quarterlyRows[row - quarterlyStart];
  effectiveRateFormulas.push([item.deposit_type === "Non-interest-bearing deposits" ? "=0" : `=D${row}*4/C${row}`]);
  if (["Checking", "Savings", "Time deposits"].includes(item.deposit_type)) {
    const totalRow = quarterlyRowMap.get(`${item.period}|Total interest-bearing deposits`);
    shareFormulas.push([`=C${row}/C${totalRow}`]);
  } else if (item.deposit_type === "Total interest-bearing deposits") {
    shareFormulas.push(["=1"]);
  } else {
    shareFormulas.push(["=\"\""]);
  }
}
sources.getRange(`F${quarterlyStart}:F${quarterlyEnd}`).formulas = effectiveRateFormulas;
sources.getRange(`G${quarterlyStart}:G${quarterlyEnd}`).formulas = shareFormulas;
sources.getRange(`C${quarterlyStart}:D${quarterlyEnd}`).format.numberFormat = "#,##0.0;(#,##0.0);-";
sources.getRange(`E${quarterlyStart}:G${quarterlyEnd}`).format.numberFormat = "0.00%";
sources.getRange(`A${quarterlyStart}:H${quarterlyEnd}`).format.font = { name: fontName, size: 10, color: black };
sources.getRange(`C${quarterlyStart}:E${quarterlyEnd}`).format.fill = lighter;
sources.getRange(`C${quarterlyStart}:E${quarterlyEnd}`).format.font = { name: fontName, size: 10, color: blue };

// Sources: non-interest-bearing quarter-end anchors.
sources.getRange("A93:J93").merge();
sources.getRange("A93").values = [["Non-interest-bearing quarter-end anchors"]];
setSectionTitle(sources.getRange("A93:J93"));
sources.getRange("A95:C95").values = [["Period End", "Non-Interest-Bearing EOP Balance ($mm)", "Source Form"]];
setDarkHeader(sources.getRange("A95:C95"));
const anchorStart = 96;
const anchorRows = [...sourceData.noninterest_eop_anchors].sort((a, b) => a.period_end.localeCompare(b.period_end));
const anchorEnd = anchorStart + anchorRows.length - 1;
sources.getRange(`A${anchorStart}:C${anchorEnd}`).values = anchorRows.map((row) => [
  new Date(`${row.period_end}T00:00:00Z`),
  row.eop_balance_mm,
  row.source_form,
]);
sources.getRange(`A${anchorStart}:A${anchorEnd}`).format.numberFormat = "mmm-yy";
sources.getRange(`B${anchorStart}:B${anchorEnd}`).format.numberFormat = "#,##0.0;(#,##0.0);-";
sources.getRange(`A${anchorStart}:C${anchorEnd}`).format.font = { name: fontName, size: 10, color: blue };
sources.getRange(`A${anchorStart}:C${anchorEnd}`).format.fill = lighter;
const anchorRowMap = new Map(anchorRows.map((row, index) => [row.period_end, anchorStart + index]));

// Sources: monthly controlled inputs and NIB build.
sources.getRange("A58:J58").merge();
sources.getRange("A58").values = [["Monthly controlled inputs and non-interest-bearing balance build"]];
setSectionTitle(sources.getRange("A58:J58"));
sources.getRange("A60:J60").values = [[
  "Month",
  "Source Period",
  "Controlled IB Average Balance ($mm)",
  "Controlled IB Interest Expense ($mm)",
  "Controlled IB Rate",
  "Prior Quarter-End NIB Balance ($mm)",
  "Current Quarter-End NIB Balance ($mm)",
  "Reported Quarterly NIB Average ($mm)",
  "Derived Month-End NIB Balance ($mm)",
  "Derived Monthly NIB Average ($mm)",
]];
setDarkHeader(sources.getRange("A60:J60"));
const controlStart = 61;
const controlEnd = controlStart + monthlyControls.length - 1;
sources.getRange(`A${controlStart}:J${controlEnd}`).values = monthlyControls.map((row) => {
  return [
    row.month,
    row.period,
    row.totalIbBalance,
    row.totalIbExpense,
    row.totalIbRate,
    null,
    null,
    null,
    null,
    null,
  ];
});
const controlRowMap = new Map(monthlyControls.map((row, index) => [row.monthKey, controlStart + index]));

const priorAnchorFormulas = [];
const currentAnchorFormulas = [];
const reportedNibFormulas = [];
const derivedEopFormulas = [];
const derivedAvgFormulas = [];
for (let index = 0; index < monthlyControls.length; index += 1) {
  const item = monthlyControls[index];
  const sheetRow = controlStart + index;
  const priorAnchorRow = anchorRowMap.get(previousQuarterEnd(item.year, item.quarter));
  const currentAnchorRow = anchorRowMap.get(currentQuarterEnd(item.year, item.quarter));
  const nibQuarterRow = quarterlyRowMap.get(`${item.period}|Non-interest-bearing deposits`);
  if (!priorAnchorRow || !currentAnchorRow || !nibQuarterRow) {
    throw new Error(`Missing NIB build source for ${item.monthKey}`);
  }
  priorAnchorFormulas.push([`=$B$${priorAnchorRow}`]);
  currentAnchorFormulas.push([`=$B$${currentAnchorRow}`]);
  reportedNibFormulas.push([`=$C$${nibQuarterRow}`]);
  const monthInQuarter = (item.month.getUTCMonth() % 3) + 1;
  if (monthInQuarter === 1) {
    derivedEopFormulas.push([`=F${sheetRow}+(G${sheetRow}-F${sheetRow})/3+(2*H${sheetRow}-F${sheetRow}-G${sheetRow})`]);
    derivedAvgFormulas.push([`=AVERAGE(F${sheetRow},I${sheetRow})`]);
  } else if (monthInQuarter === 2) {
    derivedEopFormulas.push([`=F${sheetRow}+2*(G${sheetRow}-F${sheetRow})/3+(2*H${sheetRow}-F${sheetRow}-G${sheetRow})`]);
    derivedAvgFormulas.push([`=AVERAGE(I${sheetRow - 1},I${sheetRow})`]);
  } else {
    derivedEopFormulas.push([`=G${sheetRow}`]);
    derivedAvgFormulas.push([`=AVERAGE(I${sheetRow - 1},I${sheetRow})`]);
  }
}
sources.getRange(`F${controlStart}:F${controlEnd}`).formulas = priorAnchorFormulas;
sources.getRange(`G${controlStart}:G${controlEnd}`).formulas = currentAnchorFormulas;
sources.getRange(`H${controlStart}:H${controlEnd}`).formulas = reportedNibFormulas;
sources.getRange(`I${controlStart}:I${controlEnd}`).formulas = derivedEopFormulas;
sources.getRange(`J${controlStart}:J${controlEnd}`).formulas = derivedAvgFormulas;
sources.getRange(`A${controlStart}:A${controlEnd}`).format.numberFormat = "mmm-yy";
sources.getRange(`C${controlStart}:D${controlEnd}`).format.numberFormat = "#,##0.0;(#,##0.0);-";
sources.getRange(`E${controlStart}:E${controlEnd}`).format.numberFormat = "0.00%";
sources.getRange(`F${controlStart}:J${controlEnd}`).format.numberFormat = "#,##0.0;(#,##0.0);-";
sources.getRange(`A${controlStart}:J${controlEnd}`).format.font = { name: fontName, size: 10, color: black };
sources.getRange(`A${controlStart}:E${controlEnd}`).format.fill = lighter;
sources.getRange(`A${controlStart}:E${controlEnd}`).format.font = { name: fontName, size: 10, color: blue };

// Main output: title and period summary.
output.getRange("A2").values = [["Capital One deposit rate and balance actuals"]];
output.getRange("A2").format.font = { name: fontName, size: 14, bold: true, color: dark };
output.getRange("A3:O3").merge();
output.getRange("A3").values = [["Monthly actuals from Jan-2024 through Jun-2026. Balances and monthly interest expense are in $ millions; rates are annualized."]];
output.getRange("A3").format.font = { name: fontName, size: 9, italic: true, color: mid };
output.getRange("A3:O3").format.borders = { bottom: { style: "medium", color: red } };

output.getRange("A5:K5").values = [[
  "Period",
  "Start Month",
  "Through Month",
  "Checking Avg Balance",
  "Savings Avg Balance",
  "Time Deposits Avg Balance",
  "Total IB Avg Balance",
  "NIB Avg Balance",
  "Total Deposits Avg Balance",
  "IB Average Rate",
  "Total Deposit Cost",
]];
setDarkHeader(output.getRange("A5:K5"));
output.getRange("A6:C8").values = [
  ["2024", new Date(Date.UTC(2024, 0, 31)), new Date(Date.UTC(2024, 11, 31))],
  ["2025", new Date(Date.UTC(2025, 0, 31)), new Date(Date.UTC(2025, 11, 31))],
  ["H1 2026", new Date(Date.UTC(2026, 0, 31)), new Date(Date.UTC(2026, 5, 30))],
];
output.getRange("B6:C8").format.numberFormat = "mmm-yy";

const detailStart = 13;
const detailEnd = detailStart + monthlyControls.length * outputOrder.length - 1;
const summaryBalanceTypes = ["Checking", "Savings", "Time deposits", "Total interest-bearing deposits", "Non-interest-bearing deposits", "Total deposits"];
for (let col = 0; col < summaryBalanceTypes.length; col += 1) {
  const headerCol = String.fromCharCode("D".charCodeAt(0) + col);
  output.getRange(`${headerCol}6`).formulas = [[`=SUMIFS($F$${detailStart}:$F$${detailEnd},$D$${detailStart}:$D$${detailEnd},"${summaryBalanceTypes[col]}",$A$${detailStart}:$A$${detailEnd},">="&$B6,$A$${detailStart}:$A$${detailEnd},"<="&$C6)/COUNTIFS($D$${detailStart}:$D$${detailEnd},"${summaryBalanceTypes[col]}",$A$${detailStart}:$A$${detailEnd},">="&$B6,$A$${detailStart}:$A$${detailEnd},"<="&$C6)`]];
  output.getRange(`${headerCol}6:${headerCol}8`).fillDown();
}
output.getRange("J6").formulas = [[`=SUMIFS($H$${detailStart}:$H$${detailEnd},$D$${detailStart}:$D$${detailEnd},"Total interest-bearing deposits",$A$${detailStart}:$A$${detailEnd},">="&$B6,$A$${detailStart}:$A$${detailEnd},"<="&$C6)*12/SUMIFS($F$${detailStart}:$F$${detailEnd},$D$${detailStart}:$D$${detailEnd},"Total interest-bearing deposits",$A$${detailStart}:$A$${detailEnd},">="&$B6,$A$${detailStart}:$A$${detailEnd},"<="&$C6)`]];
output.getRange("J6:J8").fillDown();
output.getRange("K6").formulas = [[`=SUMIFS($H$${detailStart}:$H$${detailEnd},$D$${detailStart}:$D$${detailEnd},"Total deposits",$A$${detailStart}:$A$${detailEnd},">="&$B6,$A$${detailStart}:$A$${detailEnd},"<="&$C6)*12/SUMIFS($F$${detailStart}:$F$${detailEnd},$D$${detailStart}:$D$${detailEnd},"Total deposits",$A$${detailStart}:$A$${detailEnd},">="&$B6,$A$${detailStart}:$A$${detailEnd},"<="&$C6)`]];
output.getRange("K6:K8").fillDown();
output.getRange("D6:I8").format.numberFormat = "#,##0.0;(#,##0.0);-";
output.getRange("J6:K8").format.numberFormat = "0.00%";
output.getRange("A6:K8").format.font = { name: fontName, size: 10, color: black };
output.getRange("A6:K8").format.borders = { bottom: { style: "thin", color: light } };
output.getRange("A6:K8").format.fill = lighter;
output.getRange("A6:A8").format.font = { name: fontName, size: 10, bold: true, color: dark };

const detailHeaders = [[
  "Month",
  "Year",
  "Quarter",
  "Deposit Type",
  "Interest Bearing",
  "Average Balance ($mm)",
  "Annualized Rate",
  "Monthly Interest Expense ($mm)",
  "Share of Total Deposits",
  "MoM Balance Change ($mm)",
  "MoM Balance Change (%)",
  "YoY Balance Change (%)",
  "Source Period",
  "Source Method",
  "Data Status",
]];
output.getRange("A12:O12").values = detailHeaders;
setDarkHeader(output.getRange("A12:O12"));

const detailValues = [];
const detailFormulas = [];
for (let monthIndex = 0; monthIndex < monthlyControls.length; monthIndex += 1) {
  const item = monthlyControls[monthIndex];
  const controlRow = controlRowMap.get(item.monthKey);
  const groupStart = detailStart + monthIndex * outputOrder.length;
  const totalIbRow = groupStart + 3;
  const nibRow = groupStart + 4;
  const totalDepositsRow = groupStart + 5;
  const disclosure = quarterIndex.get(`${item.period}|Total interest-bearing deposits`);
  for (let typeIndex = 0; typeIndex < outputOrder.length; typeIndex += 1) {
    const depositType = outputOrder[typeIndex];
    const row = groupStart + typeIndex;
    const interestBearing = depositType === "Non-interest-bearing deposits" ? "No" : depositType === "Total deposits" ? "Mixed" : "Yes";
    let sourceMethod;
    let dataStatus;
    if (["Checking", "Savings", "Time deposits"].includes(depositType)) {
      sourceMethod = "Quarter balance and expense mix applied to controlled totals";
      dataStatus = disclosure.method.startsWith("Derived Q4") ? "Allocated from derived Q4 actual" : "Allocated from reported quarter actual";
    } else if (depositType === "Total interest-bearing deposits") {
      sourceMethod = "Controlled monthly imputation";
      dataStatus = "Controlled monthly actual estimate";
    } else if (depositType === "Non-interest-bearing deposits") {
      sourceMethod = "Quarterly average and EOP controlled interpolation";
      dataStatus = disclosure.method.startsWith("Derived Q4") ? "Controlled monthly estimate using derived Q4" : "Controlled monthly actual estimate";
    } else {
      sourceMethod = "Interest-bearing plus non-interest-bearing deposits";
      dataStatus = "Calculated monthly total";
    }
    detailValues.push([
      item.month,
      item.year,
      `Q${item.quarter}`,
      depositType,
      interestBearing,
      null,
      null,
      null,
      null,
      null,
      null,
      null,
      item.period,
      sourceMethod,
      dataStatus,
    ]);

    let balanceFormula;
    let rateFormula;
    let expenseFormula;
    if (["Checking", "Savings", "Time deposits"].includes(depositType)) {
      const quarterRow = quarterlyRowMap.get(`${item.period}|${depositType}`);
      balanceFormula = `='Sources & Checks'!$C$${controlRow}*'Sources & Checks'!$G$${quarterRow}`;
      const quarterTotalRow = quarterlyRowMap.get(`${item.period}|Total interest-bearing deposits`);
      expenseFormula = `='Sources & Checks'!$D$${controlRow}*'Sources & Checks'!$D$${quarterRow}/'Sources & Checks'!$D$${quarterTotalRow}`;
      rateFormula = `=H${row}*12/F${row}`;
    } else if (depositType === "Total interest-bearing deposits") {
      balanceFormula = `=SUM(F${groupStart}:F${groupStart + 2})`;
      rateFormula = `=H${row}*12/F${row}`;
      expenseFormula = `=SUM(H${groupStart}:H${groupStart + 2})`;
    } else if (depositType === "Non-interest-bearing deposits") {
      balanceFormula = `='Sources & Checks'!$J$${controlRow}`;
      rateFormula = "=0";
      expenseFormula = "=0";
    } else {
      balanceFormula = `=SUM(F${totalIbRow},F${nibRow})`;
      rateFormula = `=H${row}*12/F${row}`;
      expenseFormula = `=SUM(H${totalIbRow},H${nibRow})`;
    }
    const shareFormula = `=F${row}/F${totalDepositsRow}`;
    const momAmountFormula = monthIndex === 0 ? "=\"\"" : `=F${row}-F${row - 6}`;
    const momPctFormula = monthIndex === 0 ? "=\"\"" : `=IF(F${row - 6}=0,"n.a.",F${row}/F${row - 6}-1)`;
    const yoyPctFormula = monthIndex < 12 ? "=\"\"" : `=IF(F${row - 72}=0,"n.a.",F${row}/F${row - 72}-1)`;
    detailFormulas.push([balanceFormula, rateFormula, expenseFormula, shareFormula, momAmountFormula, momPctFormula, yoyPctFormula]);
  }
}
output.getRange(`A${detailStart}:O${detailEnd}`).values = detailValues;
output.getRange(`F${detailStart}:L${detailEnd}`).formulas = detailFormulas;
output.getRange(`A${detailStart}:A${detailEnd}`).format.numberFormat = "mmm-yy";
output.getRange(`F${detailStart}:F${detailEnd}`).format.numberFormat = "#,##0.0;(#,##0.0);-";
output.getRange(`G${detailStart}:G${detailEnd}`).format.numberFormat = "0.00%";
output.getRange(`H${detailStart}:H${detailEnd}`).format.numberFormat = "#,##0.0;(#,##0.0);-";
output.getRange(`I${detailStart}:I${detailEnd}`).format.numberFormat = "0.0%";
output.getRange(`J${detailStart}:J${detailEnd}`).format.numberFormat = "#,##0.0;(#,##0.0);-";
output.getRange(`K${detailStart}:L${detailEnd}`).format.numberFormat = "0.0%";
output.getRange(`A${detailStart}:O${detailEnd}`).format.font = { name: fontName, size: 10, color: black };
output.getRange(`A${detailStart}:O${detailEnd}`).format.verticalAlignment = "center";

const detailTable = output.tables.add(`A12:O${detailEnd}`, true, "DepositActualsTable");
detailTable.style = "TableStyleMedium2";
setDarkHeader(output.getRange("A12:O12"));

for (let monthIndex = 0; monthIndex < monthlyControls.length; monthIndex += 1) {
  const groupStart = detailStart + monthIndex * 6;
  const totalIbRow = groupStart + 3;
  const totalDepositsRow = groupStart + 5;
  output.getRange(`A${groupStart}:O${groupStart}`).format.borders = { top: { style: "thin", color: light } };
  output.getRange(`A${totalIbRow}:O${totalIbRow}`).format.fill = light;
  output.getRange(`A${totalIbRow}:O${totalIbRow}`).format.font = { name: fontName, size: 10, bold: true, color: dark };
  output.getRange(`A${totalDepositsRow}:O${totalDepositsRow}`).format.fill = totalFill;
  output.getRange(`A${totalDepositsRow}:O${totalDepositsRow}`).format.font = { name: fontName, size: 10, bold: true, color: dark };
  output.getRange(`A${totalDepositsRow}:O${totalDepositsRow}`).format.borders = { bottom: { style: "medium", color: mid } };
}

// Terminal reconciliation checks. These do not feed the output.
sources.getRange("N5:R5").values = [["Month", "IB Balance Difference", "IB Expense Difference", "NIB Quarter-End Difference", "Status"]];
setDarkHeader(sources.getRange("N5:R5"));
const monthlyCheckFormulas = [];
for (let index = 0; index < monthlyControls.length; index += 1) {
  const sourceRow = controlStart + index;
  const outputTotalIbRow = detailStart + index * 6 + 3;
  const monthInQuarter = (monthlyControls[index].month.getUTCMonth() % 3) + 1;
  monthlyCheckFormulas.push([
    `='Deposit Actuals'!A${outputTotalIbRow}`,
    `=ROUND('Deposit Actuals'!F${outputTotalIbRow}-C${sourceRow},2)`,
    `=ROUND('Deposit Actuals'!H${outputTotalIbRow}-D${sourceRow},2)`,
    monthInQuarter === 3 ? `=ROUND(I${sourceRow}-G${sourceRow},2)` : "=\"\"",
    monthInQuarter === 3
      ? `=IF(AND(ABS(O${6 + index})<0.01,ABS(P${6 + index})<0.01,ABS(Q${6 + index})<0.01),"OK","Review")`
      : `=IF(AND(ABS(O${6 + index})<0.01,ABS(P${6 + index})<0.01),"OK","Review")`,
  ]);
}
sources.getRange("N6:R35").formulas = monthlyCheckFormulas;
sources.getRange("N6:N35").format.numberFormat = "mmm-yy";
sources.getRange("O6:Q35").format.numberFormat = "0.00;(0.00);0.00";
sources.getRange("N6:R35").format.font = { name: fontName, size: 10, color: black };
sources.getRange("R6:R35").conditionalFormats.add("containsText", {
  text: "Review",
  format: { fill: errorFill, font: { bold: true, color: errorText } },
});

sources.getRange("N39:Q39").values = [["Source Period", "Product Balance Difference", "Product Interest Difference", "Status"]];
setDarkHeader(sources.getRange("N39:Q39"));
const periods = [...new Set(monthlyControls.map((row) => row.period))];
const quarterCheckFormulas = [];
for (let index = 0; index < periods.length; index += 1) {
  const period = periods[index];
  const checkingRow = quarterlyRowMap.get(`${period}|Checking`);
  const savingsRow = quarterlyRowMap.get(`${period}|Savings`);
  const timeRow = quarterlyRowMap.get(`${period}|Time deposits`);
  const totalRow = quarterlyRowMap.get(`${period}|Total interest-bearing deposits`);
  const row = 40 + index;
  quarterCheckFormulas.push([
    `="${period}"`,
    `=ROUND(SUM(C${checkingRow},C${savingsRow},C${timeRow})-C${totalRow},2)`,
    `=ROUND(SUM(D${checkingRow},D${savingsRow},D${timeRow})-D${totalRow},2)`,
    `=IF(AND(ABS(O${row})<0.01,ABS(P${row})<0.01),"OK","Review")`,
  ]);
}
sources.getRange(`N40:Q${39 + periods.length}`).formulas = quarterCheckFormulas;
sources.getRange(`O40:P${39 + periods.length}`).format.numberFormat = "0.00;(0.00);0.00";
sources.getRange(`N40:Q${39 + periods.length}`).format.font = { name: fontName, size: 10, color: black };
sources.getRange(`Q40:Q${39 + periods.length}`).conditionalFormats.add("containsText", {
  text: "Review",
  format: { fill: errorFill, font: { bold: true, color: errorText } },
});

sources.getRange("A109:L109").merge();
sources.getRange("A109").values = [["Methodology"]];
setSectionTitle(sources.getRange("A109:L109"));
sources.getRange("A111:A117").values = [
  ["Checking, savings, and time-deposit monthly balances use each reported quarter's average balance mix applied to the controlled monthly interest-bearing total."],
  ["Monthly product interest expense uses each reported quarter's interest-expense mix applied to the controlled monthly total. Monthly product rates are recalculated from allocated expense and balance, preserving both reported quarterly product expense and the controlled monthly total."],
  ["Q4 average balances equal (full-year average times 12 less nine-month average times 9) divided by 3. Q4 interest expense equals full-year less nine-month expense."],
  ["Non-interest-bearing monthly balances use reported quarterly averages and reported quarter-end balances. The month-end path follows the controlled workbook's four-point average method; monthly averages are two-point averages."],
  ["Total interest-bearing deposits equal checking plus savings plus time deposits. Total deposits equal interest-bearing plus non-interest-bearing deposits."],
  ["Monthly product splits and non-interest-bearing balances are controlled estimates because Capital One reports these measures quarterly, not monthly."],
  ["Source basis: Capital One Forms 10-K and 10-Q, including average-balance and deposit-composition disclosures, plus the controlled monthly deposit workbook."],
];
sources.getRange("A111:L117").merge(true);
sources.getRange("A111:L117").format.font = { name: fontName, size: 10, color: black };
sources.getRange("A111:L117").format.wrapText = true;
sources.getRange("A111:L117").format.rowHeight = 28;

// Layout and sizing.
output.getRange("A2").format.font = { name: fontName, size: 14, bold: true, color: dark };
output.getRange("A:A").format.columnWidth = 11;
output.getRange("B:B").format.columnWidth = 8;
output.getRange("C:C").format.columnWidth = 9;
output.getRange("D:D").format.columnWidth = 31;
output.getRange("E:E").format.columnWidth = 15;
output.getRange("F:F").format.columnWidth = 16;
output.getRange("G:G").format.columnWidth = 14;
output.getRange("H:H").format.columnWidth = 19;
output.getRange("I:I").format.columnWidth = 16;
output.getRange("J:J").format.columnWidth = 18;
output.getRange("K:L").format.columnWidth = 15;
output.getRange("M:M").format.columnWidth = 13;
output.getRange("N:N").format.columnWidth = 52;
output.getRange("O:O").format.columnWidth = 38;
output.getRange("A12:O12").format.rowHeight = 36;
output.getRange(`A${detailStart}:O${detailEnd}`).format.rowHeight = 19;
output.getRange(`A${detailStart}:E${detailEnd}`).format.horizontalAlignment = "left";
output.getRange(`F${detailStart}:L${detailEnd}`).format.horizontalAlignment = "right";
output.getRange(`M${detailStart}:O${detailEnd}`).format.horizontalAlignment = "left";
output.freezePanes.freezeRows(12);
output.freezePanes.freezeColumns(4);

sources.getRange("A:A").format.columnWidth = 14;
sources.getRange("B:B").format.columnWidth = 31;
sources.getRange("C:D").format.columnWidth = 18;
sources.getRange("E:G").format.columnWidth = 17;
sources.getRange("H:H").format.columnWidth = 42;
sources.getRange("I:J").format.columnWidth = 18;
sources.getRange("K:L").format.columnWidth = 3;
sources.getRange("M:M").format.columnWidth = 3;
sources.getRange("N:N").format.columnWidth = 13;
sources.getRange("O:Q").format.columnWidth = 18;
sources.getRange("R:R").format.columnWidth = 12;
sources.getRange("A5:R117").format.verticalAlignment = "center";
sources.getRange("A5:H5").format.rowHeight = 34;
sources.getRange("A60:J60").format.rowHeight = 42;
sources.getRange("N5:R5").format.rowHeight = 34;
sources.getRange("N39:Q39").format.rowHeight = 34;
sources.freezePanes.freezeRows(5);

workbook.recalculate();

const outputInspect = await workbook.inspect({
  kind: "table",
  range: `Deposit Actuals!A1:O25`,
  include: "values,formulas",
  tableMaxRows: 25,
  tableMaxCols: 15,
  maxChars: 18000,
});
console.log("OUTPUT_INSPECT");
console.log(outputInspect.ndjson);

const checkInspect = await workbook.inspect({
  kind: "table",
  range: "Sources & Checks!N5:R49",
  include: "values,formulas",
  tableMaxRows: 50,
  tableMaxCols: 5,
  maxChars: 18000,
});
console.log("CHECKS_INSPECT");
console.log(checkInspect.ndjson);

const errorScan = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log("ERROR_SCAN");
console.log(errorScan.ndjson);

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

for (const previewSpec of [
  { sheetName: "Deposit Actuals", range: "A1:O40", file: "deposit-actuals-top.png" },
  { sheetName: "Deposit Actuals", range: `A${detailEnd - 17}:O${detailEnd}`, file: "deposit-actuals-end.png" },
  { sheetName: "Sources & Checks", range: "A1:R50", file: "sources-checks-top.png" },
  { sheetName: "Sources & Checks", range: "A55:L117", file: "sources-checks-build.png" },
]) {
  const preview = await workbook.render({ sheetName: previewSpec.sheetName, range: previewSpec.range, scale: 1.15, format: "png" });
  await fs.writeFile(path.join(previewDir, previewSpec.file), new Uint8Array(await preview.arrayBuffer()));
}

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);

const reopened = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
reopened.recalculate();
const reopenedErrors = await reopened.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "reopened formula error scan",
});
const reopenedChecks = await reopened.inspect({
  kind: "match",
  searchTerm: "Review",
  options: { useRegex: false, maxResults: 100 },
  summary: "reopened reconciliation status scan",
});
const reopenedSourceFileScan = await reopened.inspect({
  kind: "match",
  searchTerm: "Source Fil",
  options: { useRegex: false, maxResults: 100 },
  summary: "reopened source-file label scan",
});
console.log("REOPENED_ERROR_SCAN");
console.log(reopenedErrors.ndjson);
console.log("REOPENED_REVIEW_SCAN");
console.log(reopenedChecks.ndjson);
console.log("REOPENED_SOURCE_FILE_SCAN");
console.log(reopenedSourceFileScan.ndjson);
console.log(`OUTPUT_PATH=${outputPath}`);
