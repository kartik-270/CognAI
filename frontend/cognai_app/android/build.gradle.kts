allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

subprojects {
    val configureCompileSdk: Project.() -> Unit = {
        val androidExt = extensions.findByName("android")
        if (androidExt != null) {
            for (m in androidExt.javaClass.methods) {
                if (m.name in listOf("setCompileSdk", "compileSdkVersion", "setCompileSdkVersion") &&
                    m.parameterCount == 1 &&
                    (m.parameterTypes[0] == Int::class.javaPrimitiveType || m.parameterTypes[0] == Integer::class.java)
                ) {
                    try {
                        m.invoke(androidExt, 36)
                    } catch (_: Exception) {}
                }
            }
        }
    }

    if (state.executed) {
        configureCompileSdk()
    } else {
        afterEvaluate { configureCompileSdk() }
    }
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
