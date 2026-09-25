import Testing
@testable import Terminal

@Suite("Row dates")
struct DateLabelTests {
    @Test("A calendar date reads as weekday, day and month", arguments: [
        ("2026-09-26", "Sat 26 Sep"),
        ("2026-01-01", "Thu 1 Jan"),
        ("2028-02-29", "Tue 29 Feb"),
        ("2026-12-31", "Thu 31 Dec"),
    ])
    func label(_ iso: String, _ expected: String) {
        #expect(DateLabel.route(iso) == expected)
    }

    @Test("Anything that is not a real calendar date has no label", arguments: [
        "unknown", "", "2026-02-29", "2026-02-31", "2026-13-01", "2026-9-5", "26-09-2026", "2026-09-26T10:00",
    ])
    func noLabel(_ iso: String) {
        #expect(DateLabel.route(iso) == nil)
    }
}
