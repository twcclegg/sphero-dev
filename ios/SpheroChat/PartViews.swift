import Charts
import SpheroChatCore
import SwiftUI
import UIKit

/// A program, syntax highlighted, with a copy button.
struct CodeBlockView: View {
    let part: CodePart
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(part.title ?? part.language)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Button {
                    UIPasteboard.general.string = part.code
                    copied = true
                } label: {
                    Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc")
                        .font(.caption)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color(.tertiarySystemBackground))

            ScrollView(.horizontal) {
                Text(highlighted)
                    .font(.system(.callout, design: .monospaced))
                    .textSelection(.enabled)
                    .fixedSize(horizontal: true, vertical: false)
                    .padding(12)
            }
        }
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color(.separator), lineWidth: 0.5))
    }

    private var highlighted: AttributedString {
        let tokens = part.language == "python"
            ? PythonHighlighter.tokenize(part.code) : [Token(part.code, .plain)]
        var out = AttributedString()
        for token in tokens {
            var run = AttributedString(token.text)
            run.foregroundColor = Self.color(token.kind)
            out.append(run)
        }
        return out
    }

    static func color(_ kind: TokenKind) -> Color {
        switch kind {
        case .plain: .primary
        case .keyword: .pink
        case .builtin: .purple
        case .edu: .blue
        case .string: .red
        case .comment: .secondary
        case .number: .orange
        case .definition: .teal
        case .decorator: .brown
        }
    }
}

/// A path seen from above (x right, y forward, equal scales) or a value over time.
struct ChartPartView: View {
    let part: ChartPart

    private struct Point: Identifiable {
        let id: Int
        let series: String
        let x: Double
        let y: Double
    }

    private var points: [Point] {
        var out: [Point] = []
        for s in part.series {
            for p in s.points where p.count >= 2 {
                out.append(Point(id: out.count, series: s.name, x: p[0], y: p[1]))
            }
        }
        return out
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(part.title)
                .font(.subheadline.weight(.semibold))
            if part.kind == .path {
                pathChart
            } else {
                lineChart
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color(.secondarySystemBackground)))
    }

    private var lineChart: some View {
        Chart(points) { p in
            LineMark(x: .value(part.xLabel, p.x), y: .value(part.yLabel, p.y),
                     series: .value("Series", p.series))
                .foregroundStyle(by: .value("Series", p.series))
        }
        .chartXAxisLabel(part.xLabel)
        .chartYAxisLabel(part.yLabel)
        .frame(height: 220)
    }

    private var pathChart: some View {
        let pts = points
        let (xs, ys) = Self.squareDomain(pts)
        return Chart {
            // Points are joined in the order they came, so the line follows the robot.
            ForEach(pts) { p in
                LineMark(x: .value(part.xLabel, p.x), y: .value(part.yLabel, p.y),
                         series: .value("Series", p.series))
            }
            if let first = pts.first {
                PointMark(x: .value(part.xLabel, first.x), y: .value(part.yLabel, first.y))
                    .foregroundStyle(.green)
                    .annotation(position: .top) { Text("start").font(.caption2) }
            }
            if let last = pts.last, pts.count > 1 {
                PointMark(x: .value(part.xLabel, last.x), y: .value(part.yLabel, last.y))
                    .foregroundStyle(.red)
                    .annotation(position: .top) { Text("end").font(.caption2) }
            }
        }
        .chartXScale(domain: xs)
        .chartYScale(domain: ys)
        .chartXAxisLabel(part.xLabel)
        .chartYAxisLabel(part.yLabel)
        .aspectRatio(1, contentMode: .fit)
        .frame(maxWidth: 420, maxHeight: 420)
    }

    /// Same span on both axes, so a circle looks like a circle.
    private static func squareDomain(_ pts: [Point]) -> (ClosedRange<Double>, ClosedRange<Double>) {
        let xs = pts.map(\.x), ys = pts.map(\.y)
        let (x0, x1) = (xs.min() ?? 0, xs.max() ?? 0)
        let (y0, y1) = (ys.min() ?? 0, ys.max() ?? 0)
        let half = max(x1 - x0, y1 - y0, 20) * 0.55
        let (cx, cy) = ((x0 + x1) / 2, (y0 + y1) / 2)
        return ((cx - half)...(cx + half), (cy - half)...(cy + half))
    }
}

/// Rows of sensor readings; Share sends them as CSV.
struct TablePartView: View {
    let part: TablePart

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                if let title = part.title {
                    Text(title).font(.subheadline.weight(.semibold))
                }
                Spacer()
                ShareLink(item: part.csv, preview: SharePreview("\(part.title ?? "Table") (CSV)")) {
                    Label("CSV", systemImage: "square.and.arrow.up").font(.caption)
                }
            }
            ScrollView(.horizontal) {
                Grid(alignment: .trailing, horizontalSpacing: 18, verticalSpacing: 6) {
                    GridRow {
                        ForEach(part.columns.indices, id: \.self) { i in
                            Text(part.columns[i])
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)
                        }
                    }
                    Divider()
                    ForEach(part.rows.indices, id: \.self) { r in
                        GridRow {
                            ForEach(part.rows[r].indices, id: \.self) { c in
                                Text(part.rows[r][c])
                                    .font(.system(.callout, design: .monospaced))
                            }
                        }
                    }
                }
                .padding(.vertical, 4)
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color(.secondarySystemBackground)))
    }
}
