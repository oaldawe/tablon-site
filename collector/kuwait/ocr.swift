// Reads the text of one picture with the system's recognizer, Arabic and English, and prints
// one line per piece of text: its confidence, a space, and the text, in the order read.
import Foundation
import Vision

guard CommandLine.arguments.count == 2 else {
    FileHandle.standardError.write(Data("usage: ocr <picture>\n".utf8))
    exit(2)
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["ar-SA", "en-US"]
request.usesLanguageCorrection = true
let handler = VNImageRequestHandler(url: URL(fileURLWithPath: CommandLine.arguments[1]))
do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write(Data("could not read the picture: \(error)\n".utf8))
    exit(1)
}
for observation in request.results ?? [] {
    guard let candidate = observation.topCandidates(1).first else { continue }
    print(String(format: "%.2f", candidate.confidence), candidate.string)
}
