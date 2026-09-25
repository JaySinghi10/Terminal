import Testing
@testable import Terminal

@Suite("Status colours")
struct StatusStyleTests {
    @Test("Each status word takes its colour", arguments: [
        (FlightStatus.active, Palette.green),
        (.delayed, Palette.amber),
        (.diverted, Palette.amber),
        (.cancelled, Palette.red),
        (.scheduled, Ink.secondary.rgba),
        (.landed, Ink.tertiary.rgba),
        (.stale, Ink.quaternary.rgba),
    ])
    func statusWordColour(_ status: FlightStatus, _ expected: RGBA) {
        #expect(status.tone.rgba == expected)
    }

    @Test("Only live, late and cancelled are coloured; every other tone is a grey of the one ink",
          arguments: StatusTone.allCases)
    func nothingElseIsColoured(_ tone: StatusTone) {
        switch tone {
        case .live:
            #expect(tone.rgba == Palette.green)
        case .late:
            #expect(tone.rgba == Palette.amber)
        case .cancelled:
            #expect(tone.rgba == Palette.red)
        case .scheduled, .landed, .quiet:
            #expect(tone.rgba.red == Palette.ink.red)
            #expect(tone.rgba.green == Palette.ink.green)
            #expect(tone.rgba.blue == Palette.ink.blue)
        }
    }

    @Test("A stale flight reads \"no update\"")
    func staleWord() {
        #expect(FlightStatus.stale.word == "no update")
        #expect(FlightStatus.delayed.word == "delayed")
    }

    @Test("The collapsed line drops the status word and the separator after it")
    func collapsedLine() {
        let flight = FlightSummary(
            flightNumber: "UA901",
            origin: .init(code: "SFO", city: "San Francisco"),
            destination: .init(code: "LHR", city: "London"),
            flightDate: "2026-09-26",
            status: .delayed,
            statusLine: [
                StatusSegment("delayed", .late, isHead: true),
                StatusSegment(" · updated 6m ago · dep 17:25 PDT", .quiet),
                StatusSegment(" · 05:55 your time", .quiet),
            ]
        )
        #expect(flight.statusLineWithoutHead == [
            StatusSegment("updated 6m ago · dep 17:25 PDT", .quiet),
            StatusSegment(" · 05:55 your time", .quiet),
        ])
    }

    @Test("A line made only of head segments collapses to nothing")
    func collapsedLineAllHead() {
        let flight = FlightSummary(
            flightNumber: "VS26",
            origin: .init(code: "JFK", city: "New York"),
            destination: .init(code: "LHR", city: "London"),
            flightDate: "2026-09-26",
            status: .landed,
            statusLine: [
                StatusSegment("landed 07:05 BST", .landed, isHead: true),
                StatusSegment(" · 12m early", .quiet, isHead: true),
            ]
        )
        #expect(flight.statusLineWithoutHead.isEmpty)
    }

    @Test("The route names cities, and falls back to a code when a city is missing")
    func routeText() {
        let flight = FlightSummary(
            flightNumber: "BA178",
            origin: .init(code: "JFK", city: "New York"),
            destination: .init(code: "LHR", city: nil),
            flightDate: "2026-09-26",
            status: .scheduled,
            statusLine: []
        )
        #expect(flight.routeText == "New York → LHR")
        #expect(flight.id == "BA178|2026-09-26")
    }
}
