import UIKit
import UniformTypeIdentifiers

final class ShareViewController: UIViewController {
    private let status = UILabel()
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        status.text = "Add shared links to Bunkr?"
        status.numberOfLines = 0
        let save = UIButton(type: .system)
        save.setTitle("Add to queue", for: .normal)
        save.addTarget(self, action: #selector(storeLinks), for: .touchUpInside)
        let cancel = UIButton(type: .system)
        cancel.setTitle("Cancel", for: .normal)
        cancel.addAction(UIAction { _ in self.extensionContext?.completeRequest(returningItems: nil) }, for: .touchUpInside)
        let stack = UIStackView(arrangedSubviews: [status, save, cancel])
        stack.axis = .vertical
        stack.spacing = 24
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -24),
            stack.centerYAnchor.constraint(equalTo: view.centerYAnchor)
        ])
    }
    @objc private func storeLinks() {
        Task { @MainActor in
            do {
                var links: [String] = []
                for item in extensionContext?.inputItems as? [NSExtensionItem] ?? [] {
                    for provider in item.attachments ?? [] {
                        let text: String
                        if provider.canLoadObject(ofClass: URL.self) {
                            text = try await withCheckedThrowingContinuation { continuation in
                                _ = provider.loadObject(ofClass: URL.self) { value, error in
                                    if let error { continuation.resume(throwing: error) }
                                    else { continuation.resume(returning: value?.absoluteString ?? "") }
                                }
                            }
                        } else {
                            text = try await withCheckedThrowingContinuation { continuation in
                                _ = provider.loadObject(ofClass: String.self) { value, error in
                                    if let error { continuation.resume(throwing: error) }
                                    else { continuation.resume(returning: value ?? "") }
                                }
                            }
                        }
                        links += text.split(whereSeparator: \.isNewline).compactMap { LinkParser.normalize(String($0)) }
                    }
                }
                guard !links.isEmpty else { throw NSError(domain: "Bunkr", code: 2, userInfo: [NSLocalizedDescriptionKey: "Share a Bunkr album or file link."]) }
                try SharedInbox.deposit(Array(Set(links)).sorted())
                extensionContext?.completeRequest(returningItems: nil)
            } catch { status.text = error.localizedDescription }
        }
    }
}
