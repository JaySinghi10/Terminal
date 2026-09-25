import Foundation

/// Dates written the way the rows write them, in fixed English whatever the
/// phone's language, so a row never changes width or wording with the locale.
nonisolated enum DateLabel {
    private static let weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    private static let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    /// "Fri 26 Sep" from "2026-09-26", or nil when the string is not a real
    /// calendar date. A row hides its date rather than print something untrue.
    static func route(_ isoDay: String) -> String? {
        let parts = isoDay.split(separator: "-", omittingEmptySubsequences: false)
        guard parts.count == 3,
              parts[0].count == 4, parts[1].count == 2, parts[2].count == 2,
              let year = Int(parts[0]), let month = Int(parts[1]), let day = Int(parts[2])
        else { return nil }

        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let wanted = DateComponents(year: year, month: month, day: day)
        guard let date = calendar.date(from: wanted) else { return nil }

        // Calendar rolls 31 Feb over into March; a round trip catches that.
        let back = calendar.dateComponents([.year, .month, .day, .weekday], from: date)
        guard back.year == year, back.month == month, back.day == day,
              let weekday = back.weekday
        else { return nil }

        return "\(weekdays[weekday - 1]) \(day) \(months[month - 1])"
    }
}
