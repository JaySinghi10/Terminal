#if DEBUG
import Foundation

/// Sample flights for Debug builds and previews, one for each status colour.
///
/// DEBUG ONLY. This whole file is inside #if DEBUG, and so is every use of it,
/// so a Release build contains none of these flights and fails to compile if a
/// reference slips out. The React Native app shipped its fixtures by mistake.
///
/// Times are set relative to now, so the dates and countdowns look real. The
/// status lines are written the way the React Native app prints each case; the
/// rules that build real ones come with the flight card.
enum SampleFlights {
    /// In the order the watchlist sorts them: upcoming flights by departure
    /// time, then the rest newest first.
    static func all(now: Date = .now) -> [FlightSummary] {
        [delayed(now), onTime(now), cancelled(now), landed(now)]
    }

    private static let newYork = TimeZone(identifier: "America/New_York")!
    private static let sanFrancisco = TimeZone(identifier: "America/Los_Angeles")!
    private static let london = TimeZone(identifier: "Europe/London")!
    private static let frankfurt = TimeZone(identifier: "Europe/Berlin")!

    /// Delayed: an amber status word.
    private static func delayed(_ now: Date) -> FlightSummary {
        let departure = rounded(now.addingTimeInterval(70 * 60), minutes: 5, rule: .up)
        return FlightSummary(
            flightNumber: "UA901",
            origin: .init(code: "SFO", city: "San Francisco"),
            destination: .init(code: "LHR", city: "London"),
            flightDate: localDay(departure, in: sanFrancisco),
            status: .delayed,
            statusLine: [
                StatusSegment("delayed", .late, isHead: true),
                StatusSegment(" · updated 6m ago · dep \(clockWithZone(departure, in: sanFrancisco))", .quiet),
            ] + yourTime(departure, airport: sanFrancisco)
        )
    }

    /// On time: a grey status word and a green countdown.
    private static func onTime(_ now: Date) -> FlightSummary {
        let departure = rounded(now.addingTimeInterval(200 * 60), minutes: 5, rule: .up)
        return FlightSummary(
            flightNumber: "BA178",
            origin: .init(code: "JFK", city: "New York"),
            destination: .init(code: "LHR", city: "London"),
            flightDate: localDay(departure, in: newYork),
            status: .scheduled,
            statusLine: [
                StatusSegment("scheduled", .scheduled, isHead: true),
                StatusSegment(" · departs in \(countdown(departure.timeIntervalSince(now)))", .live),
            ]
        )
    }

    /// Cancelled: a red status word.
    private static func cancelled(_ now: Date) -> FlightSummary {
        let departure = rounded(now.addingTimeInterval(300 * 60), minutes: 5, rule: .up)
        return FlightSummary(
            flightNumber: "LH400",
            origin: .init(code: "FRA", city: "Frankfurt"),
            destination: .init(code: "JFK", city: "New York"),
            flightDate: localDay(departure, in: frankfurt),
            status: .cancelled,
            statusLine: [
                StatusSegment("cancelled", .cancelled, isHead: true),
                StatusSegment(" · updated 20m ago · dep \(clockWithZone(departure, in: frankfurt))", .quiet),
            ] + yourTime(departure, airport: frankfurt)
        )
    }

    /// Landed 12 minutes early: a grey status line.
    private static func landed(_ now: Date) -> FlightSummary {
        let touchdown = rounded(now.addingTimeInterval(-55 * 60), minutes: 1, rule: .down)
        let departure = touchdown.addingTimeInterval(-(6 * 60 + 55) * 60)
        return FlightSummary(
            flightNumber: "VS26",
            origin: .init(code: "JFK", city: "New York"),
            destination: .init(code: "LHR", city: "London"),
            flightDate: localDay(departure, in: newYork),
            status: .landed,
            statusLine: [
                StatusSegment("landed \(clockWithZone(touchdown, in: london))", .landed, isHead: true),
                StatusSegment(" · 12m early", .quiet, isHead: true),
            ]
        )
    }

    // MARK: - Formatting for the samples only

    private static func rounded(_ date: Date, minutes: Int, rule: FloatingPointRoundingRule) -> Date {
        let step = Double(minutes * 60)
        let steps = (date.timeIntervalSinceReferenceDate / step).rounded(rule)
        return Date(timeIntervalSinceReferenceDate: steps * step)
    }

    private static func format(_ date: Date, _ pattern: String, in zone: TimeZone) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = zone
        formatter.dateFormat = pattern
        return formatter.string(from: date)
    }

    private static func localDay(_ date: Date, in zone: TimeZone) -> String {
        format(date, "yyyy-MM-dd", in: zone)
    }

    /// "17:25 PDT". The labels are the ones the server prints; Foundation's own
    /// abbreviations say "GMT+1" where the server says "BST".
    private static func clockWithZone(_ date: Date, in zone: TimeZone) -> String {
        let summer = zone.isDaylightSavingTime(for: date)
        let label = switch zone.identifier {
        case "America/New_York": summer ? "EDT" : "EST"
        case "America/Los_Angeles": summer ? "PDT" : "PST"
        case "Europe/London": summer ? "BST" : "GMT"
        case "Europe/Berlin": summer ? "CEST" : "CET"
        default: zone.abbreviation(for: date) ?? ""
        }
        return "\(format(date, "HH:mm", in: zone)) \(label)"
    }

    /// " · 02:25 your time", only when the phone's clock differs from the
    /// airport's, with the weekday when the day differs too.
    private static func yourTime(_ date: Date, airport: TimeZone) -> [StatusSegment] {
        let phone = TimeZone.current
        let here = format(date, "HH:mm", in: phone)
        let sameDay = localDay(date, in: phone) == localDay(date, in: airport)
        if sameDay && here == format(date, "HH:mm", in: airport) { return [] }
        let text = sameDay ? "\(here) your time" : "\(here) \(format(date, "EEE", in: phone)) your time"
        return [StatusSegment(" · \(text)", .quiet)]
    }

    /// "3h 20m", as the React Native app writes a countdown.
    private static func countdown(_ interval: TimeInterval) -> String {
        let total = Int(interval / 60)
        let days = total / 1440
        let hours = (total % 1440) / 60
        let minutes = total % 60
        if days > 0 { return "\(days)d \(hours)h" }
        if hours > 0 { return minutes > 0 ? "\(hours)h \(minutes)m" : "\(hours)h" }
        return "\(minutes)m"
    }
}
#endif
