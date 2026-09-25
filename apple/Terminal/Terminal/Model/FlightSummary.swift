import Foundation

/// The app's own words for what a flight is doing.
nonisolated enum FlightStatus: String, CaseIterable, Sendable {
    case scheduled
    case active
    case delayed
    case landed
    case cancelled
    case diverted
    case stale

    /// The word a row prints. "stale" is the internal name; a person scanning a
    /// list reads "no update".
    var word: String {
        self == .stale ? "no update" : rawValue
    }
}

/// One run of a status line: its text and what it is saying.
nonisolated struct StatusSegment: Hashable, Sendable {
    let text: String
    let tone: StatusTone
    /// True for the segments that say what the flight is doing: the status word,
    /// or the departure's or landing's own words in its place. The collapsed
    /// watchlist line leaves these out.
    let isHead: Bool

    init(_ text: String, _ tone: StatusTone, isHead: Bool = false) {
        self.text = text
        self.tone = tone
        self.isHead = isHead
    }
}

/// Everything one watchlist row shows.
///
/// The status line arrives already built. The rules that build it (departure
/// phase, landing outcome, freshness, countdowns) come with the flight card,
/// ported with their tests.
nonisolated struct FlightSummary: Identifiable, Hashable, Sendable {
    nonisolated struct Place: Hashable, Sendable {
        let code: String
        let city: String?
    }

    let flightNumber: String
    let origin: Place
    let destination: Place
    /// The departure's local date, YYYY-MM-DD.
    let flightDate: String
    let status: FlightStatus
    let statusLine: [StatusSegment]

    /// "NUMBER|YYYY-MM-DD", as the React Native app keys a saved flight.
    var id: String { "\(flightNumber.uppercased())|\(flightDate)" }

    /// Cities, not codes, so the row reads for someone who does not know IATA;
    /// a missing city falls back to its code.
    var routeText: String {
        "\(origin.city ?? origin.code) → \(destination.city ?? destination.code)"
    }

    /// The status line without its head segments and without the separator the
    /// first remaining segment opened with. The collapsed watchlist line uses it.
    var statusLineWithoutHead: [StatusSegment] {
        let rest = statusLine.filter { !$0.isHead }
        guard let first = rest.first else { return [] }
        let trimmed = first.text.hasPrefix(" · ") ? String(first.text.dropFirst(3)) : first.text
        return [StatusSegment(trimmed, first.tone)] + rest.dropFirst()
    }
}
