const module = {
    mount({ route, page }) {
        // Marca a fronteira da rota enquanto sua implementação visual ainda é
        // atendida pelo frontend legado. A migração pode ocorrer rota a rota.
        page.dataset.moduleBoundary = `studio.${route}.v1`;
    },
};
export default module;
