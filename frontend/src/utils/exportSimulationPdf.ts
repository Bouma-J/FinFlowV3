import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";

import type { SimulationResult } from "@/api/types";
import { PDF_BRAND_FILL, pdfMoney, pdfText } from "@/utils/pdfHelpers";

function hexToRgb(hex: string | null | undefined): [number, number, number] {
  const raw = (hex || "#0f9488").replace("#", "").trim();
  if (raw.length !== 6 || Number.isNaN(Number.parseInt(raw, 16))) {
    return PDF_BRAND_FILL;
  }
  return [
    Number.parseInt(raw.slice(0, 2), 16),
    Number.parseInt(raw.slice(2, 4), 16),
    Number.parseInt(raw.slice(4, 6), 16),
  ];
}

function mixRgb(
  rgb: [number, number, number],
  target: "white" | "black",
  amount: number,
): [number, number, number] {
  const t = target === "white" ? 255 : 0;
  const f = Math.min(1, Math.max(0, amount));
  return [
    Math.round(rgb[0] + (t - rgb[0]) * f),
    Math.round(rgb[1] + (t - rgb[1]) * f),
    Math.round(rgb[2] + (t - rgb[2]) * f),
  ];
}

const money = pdfMoney;

function num(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  return typeof value === "number" ? value : Number(value);
}

function formatDueDate(value: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (m) return `${m[3]}/${m[2]}/${m[1]}`;
  return value || "-";
}

export type SimulationPdfParams = {
  amount: string | number;
  annualRate: string | number;
  months: string | number;
  periodicityLabel: string;
  mechanismLabel: string;
  savingsRate?: string | number;
  firstDueDate?: string;
  simulationDate?: string;
  tenantName?: string;
  brandPrimary?: string;
  brandSecondary?: string;
  brandAccent?: string;
};

export function exportSimulationPdf(
  result: SimulationResult,
  params: SimulationPdfParams,
) {
  const hasSavings = num(result.total_savings) > 0;
  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const marginX = 12;
  const contentWidth = pageWidth - marginX * 2;

  const primary = hexToRgb(params.brandPrimary);
  const secondary = hexToRgb(params.brandSecondary || params.brandPrimary);
  const accent = hexToRgb(params.brandAccent || "#d4a017");
  const softBg = mixRgb(primary, "white", 0.88);
  const stripeBg = mixRgb(primary, "white", 0.94);
  const ink: [number, number, number] = [23, 35, 31];
  const muted: [number, number, number] = [90, 100, 96];

  const org = pdfText(params.tenantName || "FIN_FLOW");
  const generatedAt = pdfText(new Date().toLocaleString("fr-FR"));

  // Bandeau filiale
  doc.setFillColor(...primary);
  doc.rect(0, 0, pageWidth, 18, "F");
  doc.setFillColor(...accent);
  doc.rect(0, 18, pageWidth, 1.2, "F");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  doc.setTextColor(255, 255, 255);
  doc.text(org, marginX, 11.5);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.text(`Genere le ${generatedAt}`, pageWidth - marginX, 11.5, {
    align: "right",
  });

  doc.setFont("helvetica", "bold");
  doc.setFontSize(12);
  doc.setTextColor(...secondary);
  doc.text("Tableau d'amortissement previsionnel", marginX, 27);

  doc.setDrawColor(...mixRgb(primary, "white", 0.55));
  doc.setLineWidth(0.3);
  doc.line(marginX, 29.5, pageWidth - marginX, 29.5);

  const summaryPairs: [string, string][] = [
    ["Montant", `${money(params.amount)} XOF`],
    ["Taux annuel", `${params.annualRate} %`],
    ["Duree", `${params.months} mois`],
    ["Periodicite", pdfText(params.periodicityLabel)],
    ["Mecanisme", pdfText(params.mechanismLabel)],
    ["Nb echeances", String(result.schedule.length)],
    ["Interets totaux", `${money(result.total_interest)} XOF`],
    [
      hasSavings ? "Total institution" : "Total a rembourser",
      `${money(
        hasSavings
          ? result.total_institution ??
              num(result.total_repayment) - num(result.total_savings)
          : result.total_repayment,
      )} XOF`,
    ],
  ];
  if (hasSavings) {
    summaryPairs.push(
      ["Epargne obligatoire", `${params.savingsRate ?? 0} %`],
      ["Epargne totale", `${money(result.total_savings)} XOF`],
      ["Total client", `${money(result.total_repayment)} XOF`],
    );
  }
  if (params.simulationDate) {
    summaryPairs.splice(5, 0, [
      "Date simulation",
      formatDueDate(params.simulationDate),
    ]);
  }
  if (params.firstDueDate) {
    summaryPairs.splice(params.simulationDate ? 6 : 5, 0, [
      "1ere echeance",
      formatDueDate(params.firstDueDate),
    ]);
  }

  autoTable(doc, {
    startY: 32,
    body: chunkPairs(summaryPairs, 3).map((row) =>
      row.flatMap(([label, value]) => [
        { content: pdfText(label), styles: { fontStyle: "bold", textColor: muted } },
        { content: pdfText(value), styles: { fontStyle: "normal", textColor: ink } },
      ]),
    ),
    theme: "plain",
    styles: {
      fontSize: 8,
      cellPadding: { top: 1.2, bottom: 1.2, left: 1, right: 2 },
      overflow: "linebreak",
      valign: "middle",
    },
    columnStyles: {
      0: { cellWidth: contentWidth / 6 },
      1: { cellWidth: contentWidth / 6 },
      2: { cellWidth: contentWidth / 6 },
      3: { cellWidth: contentWidth / 6 },
      4: { cellWidth: contentWidth / 6 },
      5: { cellWidth: contentWidth / 6 },
    },
    margin: { left: marginX, right: marginX },
    tableLineColor: softBg,
    tableLineWidth: 0,
  });

  const afterSummary =
    (doc as jsPDF & { lastAutoTable?: { finalY: number } }).lastAutoTable
      ?.finalY ?? 48;

  const head = hasSavings
    ? [
        "N°",
        "Date",
        "Capital",
        "Interet",
        "Epargne",
        "Ech. institution",
        "Total client",
        "Cap. restant",
      ]
    : [
        "N°",
        "Date",
        "Capital",
        "Interet",
        "Ech. institution",
        "Cap. restant",
      ];

  const body = result.schedule.map((row) => {
    const base = [
      String(row.number),
      formatDueDate(String(row.due_date)),
      money(row.principal),
      money(row.interest),
    ];
    if (hasSavings) {
      return [
        ...base,
        money(row.savings),
        money(row.institution_due ?? num(row.principal) + num(row.interest)),
        money(row.total),
        money(row.balance),
      ];
    }
    return [
      ...base,
      money(row.institution_due ?? num(row.principal) + num(row.interest)),
      money(row.balance),
    ];
  });

  const totalPrincipal = result.schedule.reduce(
    (s, r) => s + num(r.principal),
    0,
  );
  const foot = hasSavings
    ? [
        {
          content: "Totaux",
          colSpan: 2,
          styles: { halign: "left" as const, fontStyle: "bold" as const },
        },
        money(totalPrincipal),
        money(result.total_interest),
        money(result.total_savings),
        money(
          result.total_institution ??
            num(result.total_repayment) - num(result.total_savings),
        ),
        money(result.total_repayment),
        "-",
      ]
    : [
        {
          content: "Totaux",
          colSpan: 2,
          styles: { halign: "left" as const, fontStyle: "bold" as const },
        },
        money(totalPrincipal),
        money(result.total_interest),
        money(
          result.total_institution ??
            num(result.total_repayment) - num(result.total_savings),
        ),
        "-",
      ];

  const colCount = hasSavings ? 8 : 6;
  // Largeurs fixes pour un alignement stable (somme = contentWidth)
  const widths = hasSavings
    ? [12, 24, 36, 36, 32, 40, 40, contentWidth - 12 - 24 - 36 - 36 - 32 - 40 - 40]
    : [14, 28, 48, 48, 55, contentWidth - 14 - 28 - 48 - 48 - 55];

  const columnStyles: Record<number, { cellWidth: number; halign: "center" | "right" | "left" }> = {};
  for (let i = 0; i < colCount; i++) {
    columnStyles[i] = {
      cellWidth: widths[i],
      halign: i < 2 ? "center" : "right",
    };
  }
  columnStyles[0].halign = "center";

  autoTable(doc, {
    startY: afterSummary + 4,
    head: [head],
    body,
    foot: [foot],
    showFoot: "lastPage",
    theme: "grid",
    styles: {
      font: "helvetica",
      fontSize: hasSavings ? 7.5 : 8,
      cellPadding: { top: 1.4, bottom: 1.4, left: 1.2, right: 1.2 },
      textColor: ink,
      lineColor: mixRgb(primary, "white", 0.65),
      lineWidth: 0.15,
      overflow: "ellipsize",
      valign: "middle",
      minCellHeight: 6,
    },
    headStyles: {
      fillColor: primary,
      textColor: [255, 255, 255],
      fontStyle: "bold",
      halign: "center",
      valign: "middle",
      fontSize: hasSavings ? 7 : 8,
    },
    bodyStyles: {
      fillColor: [255, 255, 255],
    },
    alternateRowStyles: {
      fillColor: stripeBg,
    },
    footStyles: {
      fillColor: softBg,
      textColor: secondary,
      fontStyle: "bold",
      halign: "right",
      fontSize: hasSavings ? 7.5 : 8,
    },
    columnStyles,
    margin: { left: marginX, right: marginX, bottom: 14 },
    tableWidth: contentWidth,
    didParseCell(data) {
      if (data.section === "head") {
        data.cell.styles.halign = "center";
      }
      if (data.section === "body" || data.section === "foot") {
        if (data.column.index >= 2) data.cell.styles.halign = "right";
        if (data.column.index < 2) data.cell.styles.halign = "center";
      }
      if (data.section === "foot" && data.column.index === 0) {
        data.cell.styles.halign = "left";
      }
    },
    didDrawPage(data) {
      const page = data.pageNumber;
      const total = doc.getNumberOfPages();
      doc.setFont("helvetica", "normal");
      doc.setFontSize(7.5);
      doc.setTextColor(...muted);
      doc.text(
        "Simulation indicative - ACT/365, convention CBS (1ere periode theorique). Echeancier definitif au decaissement.",
        marginX,
        pageHeight - 6,
      );
      doc.setTextColor(...primary);
      doc.text(`Page ${page}/${total}`, pageWidth - marginX, pageHeight - 6, {
        align: "right",
      });
    },
  });

  const stamp = new Date().toISOString().slice(0, 10);
  doc.save(`echeancier-simulation-${stamp}.pdf`);
}

function chunkPairs(
  items: [string, string][],
  size: number,
): [string, string][][] {
  const rows: [string, string][][] = [];
  for (let i = 0; i < items.length; i += size) {
    const slice: [string, string][] = items.slice(i, i + size);
    while (slice.length < size) {
      slice.push(["", ""]);
    }
    rows.push(slice);
  }
  return rows;
}
