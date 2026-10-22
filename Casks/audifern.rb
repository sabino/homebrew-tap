cask "audifern" do
  version "0.8.4"
  sha256 "b23a6d309c85805e27b87dce44308105b0253a92e87b6f0794f38b114c4b7dee"

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
