import Foundation
import XCTest
@testable import SpheroChatCore

final class HighlighterTests: XCTestCase {
    let program = """
    # Drives a square.
    @decorated
    async def start_program():
        set_main_led({'r': 0, 'g': 0, 'b': 255})
        for side in range(4):
            await roll(side * 90, 80, 1.5)  # one side
        speak(f"done {3.5}", True)
        s = \"\"\"multi
    line\"\"\"
    """

    func testRoundTrips() {
        XCTAssertEqual(PythonHighlighter.tokenize(program).map(\.text).joined(), program)
        XCTAssertEqual(PythonHighlighter.tokenize("x = 'unterminated\ny'").map(\.text).joined(),
                       "x = 'unterminated\ny'")
    }

    func testKinds() {
        let tokens = PythonHighlighter.tokenize(program)
        func kind(_ text: String) -> TokenKind? { tokens.first { $0.text == text }?.kind }
        XCTAssertEqual(kind("# Drives a square."), .comment)
        XCTAssertEqual(kind("@decorated"), .decorator)
        XCTAssertEqual(kind("async"), .keyword)
        XCTAssertEqual(kind("start_program"), .definition)
        XCTAssertEqual(kind("set_main_led"), .edu)
        XCTAssertEqual(kind("'r'"), .string)
        XCTAssertEqual(kind("range"), .builtin)
        XCTAssertEqual(kind("1.5"), .number)
        XCTAssertEqual(kind("f\"done {3.5}\""), .string)
        XCTAssertEqual(kind("True"), .keyword)
        XCTAssertEqual(kind("\"\"\"multi\nline\"\"\""), .string)
        XCTAssertEqual(kind("# one side"), .comment)
    }
}

final class ModelTests: XCTestCase {
    struct Messages: Decodable { var messages: [ChatMessage] }

    func testDecodesServerMessages() throws {
        let json = """
        {"conversation": "abc", "messages": [
          {"role": "status", "parts": [{"type": "text", "text": "simulating"}]},
          {"role": "assistant", "parts": [
            {"type": "text", "text": "**Square**"},
            {"type": "code", "language": "python", "title": "Square", "code": "pass"},
            {"type": "chart", "title": "Path", "kind": "path", "x_label": "x", "y_label": "y",
             "series": [{"name": "path", "points": [[0, 0], [1.5, 2]]}]},
            {"type": "table", "title": "Sensors", "columns": ["t", "x"], "rows": [["0.0", "1"]]},
            {"type": "video", "url": "..."}
          ]}
        ]}
        """
        let r = try JSONDecoder.snakeCase.decode(Messages.self, from: Data(json.utf8))
        XCTAssertEqual(r.messages[0].role, .status)
        let parts = r.messages[1].parts
        XCTAssertEqual(parts[1], .code(CodePart(language: "python", title: "Square", code: "pass")))
        guard case .chart(let chart) = parts[2] else { return XCTFail("no chart") }
        XCTAssertEqual(chart.kind, .path)
        XCTAssertEqual(chart.xLabel, "x")
        XCTAssertEqual(chart.series[0].points[1], [1.5, 2])
        guard case .table(let table) = parts[3] else { return XCTFail("no table") }
        XCTAssertEqual(table.csv, "t,x\n0.0,1\n")
        XCTAssertEqual(parts[4], .unknown("video"))
        XCTAssertEqual(r.messages[1].code?.title, "Square")
    }

    func testHistoryRoundTrips() throws {
        let m = ChatMessage(role: .assistant, parts: [
            .text("hi"), .code(CodePart(code: "x = 1")),
            .chart(ChartPart(title: "t", kind: .line, xLabel: "s", yLabel: "cm/s",
                             series: [.init(name: "v", points: [[0, 1]])])),
            .table(TablePart(columns: ["a"], rows: [["1"]])),
        ])
        let data = try JSONEncoder().encode([m])
        XCTAssertEqual(try JSONDecoder().decode([ChatMessage].self, from: data), [m])
    }
}

final class MarkdownTests: XCTestCase {
    func testSplitsFences() {
        let parts = Markdown.split("Try this:\n\n```python\nset_speed(50)\n```\nThen run it.")
        XCTAssertEqual(parts, [.text("Try this:"), .code(CodePart(code: "set_speed(50)")),
                               .text("Then run it.")])
        XCTAssertEqual(Markdown.split("plain"), [.text("plain")])
        XCTAssertEqual(Markdown.split("```\nx = 1"), [.code(CodePart(code: "x = 1"))])
    }
}

