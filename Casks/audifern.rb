cask "audifern" do
  version "0.9.0"
  sha256 "9b9ddd12c06e9e03a56c9bbee96010e1a8c23a4d295de60ec80b93ccdd45e366"

  url "https://github.com/sabino/audifern/releases/download/v#{version}/Audifern-#{version}-macos-universal.dmg"
  name "Audifern"
  desc "Local Bluetooth controls for compatible hearing aids"
  homepage "https://github.com/sabino/audifern"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on macos: :sonoma

  app "Audifern.app"
end
