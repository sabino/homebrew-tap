cask "audifern" do
  version "0.8.1"
  sha256 "d53ec9fabccbd19a6845f28f9aa66d503d8c39f68aed4f27aed25ade57b46e94"

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
