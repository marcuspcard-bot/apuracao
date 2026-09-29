from pydantic import Field, model_validator

from app.schemas.boletim import Code, StrictModel


class GrupoSecoes(StrictModel):
    zona: Code
    secao_principal: Code
    secoes_agregadas: list[Code] = Field(default_factory=list, max_length=1000)


class CadastroSecoes(StrictModel):
    grupos: list[GrupoSecoes] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def unique_sections(self):
        seen = set()
        for group in self.grupos:
            for number in [group.secao_principal, *group.secoes_agregadas]:
                if int(group.zona) == 0 or int(number) == 0:
                    raise ValueError("Zona e seção devem ser maiores que zero.")
                key = (int(group.zona), int(number))
                if key in seen:
                    raise ValueError(f"Seção {number} repetida na zona {group.zona}.")
                seen.add(key)
        if len(seen) > 10000:
            raise ValueError("A lista excede o limite de 10.000 seções.")
        return self


class ConfirmarCadastro(CadastroSecoes):
    versao_lista: str = Field(pattern=r"^[a-f0-9]{64}$")
