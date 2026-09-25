import Testing
import UIKit
@testable import Terminal

@Suite("Fonts")
struct FontTests {
    @Test("The four bundled fonts load by name", arguments: FontName.all)
    func loads(_ name: String) {
        #expect(
            UIFont(name: name, size: 12) != nil,
            "\(name) did not load: check Resources/Fonts and UIAppFonts in Config/Info.plist"
        )
    }

    @Test("Every text style uses one of the bundled fonts", arguments: TextStyle.allCases)
    func styleUsesBundledFont(_ style: TextStyle) {
        #expect(FontName.all.contains(style.fontName))
    }
}
