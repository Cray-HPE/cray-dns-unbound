@Library('dst-shared@master') _

dockerBuildPipeline {
    repository = "cray"
    imagePrefix = "cray"
    app = "dns-unbound"
    name = "dns-unbound"
    description = "Cray k8s DNS resolver using unbound"
    product = "shasta-premium,shasta-standard"
    slackNotification = ["", "", false, false, true, false]
}
