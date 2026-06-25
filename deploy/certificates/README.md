# Russian trusted certificates

The Docker image installs the certificate chain currently used by
`platform-api2.max.ru` into the system certificate store:

- Russian Trusted Root CA (SSL RSA 2022)
- Russian Trusted Sub CA (SSL RSA 2024)

Official sources:

- https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt
- http://nuc-cdp.digital.gov.ru/cdp/subca_ssl_rsa2024.crt

SHA-256:

- root: `936A43FEA6E8E525BCC0F81ACD9C3D21B4FC4B9B68ACEA7906D698005AFC6504`
- sub CA: `6F9D829C8E6712444FCE3624658D8788672849C5D5B7B53FD9CF7E83EAC4193E`

Downloaded and verified against the `*.max.ru` TLS certificate chain on
2026-06-25.
