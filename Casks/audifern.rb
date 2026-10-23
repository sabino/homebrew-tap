cask "audifern" do
  version "0.9.1"
  sha256 "af0f79ed3467feffdeb6c337b08ed32848a1ae696c8cf641dfe8b72243a92710"

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
